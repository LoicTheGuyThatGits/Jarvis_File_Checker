"""Wi-Fi helper: which devices are on your home network, and why the connection is slow.

What a PC can and cannot see:
  - It CAN list the devices that answer on the network (address, hardware address, sometimes a name).
  - It CAN measure its own link: Wi-Fi signal, channel, how crowded the channel is, delay and loss to the router and to
    the internet, and how much this PC itself is sending and receiving.
  - It CANNOT see how much data another device is using. Only the router knows that.

Everything that touches Windows goes through `run` (a function that runs a command and returns its text), so the
logic can be tested with recorded outputs. Device scans are only done on networks you have confirmed are yours.

    Network(path, run).devices_text(...)     "what devices are on my wifi"
    Network(path, run).diagnose_text(...)    "why is my wifi slow"
    Network(path, run).watch(now)            the quiet background check: returns a message when things got worse
    command(text, net, remote, now)          the chat commands (with the "yes, scan" confirmation)
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import statistics
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PENDING = {"at": 0.0, "gateway": ""}
CONFIRM_SECONDS = 180
WATCH_EVERY = 300          # seconds between background checks
WATCH_COOLDOWN = 1800      # at most one "it got slow" message per half hour
INTERNET_HOST = "1.1.1.1"
PS = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"]
PS_CONFIG = ("Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.NetAdapter.Status -eq 'Up' } | ForEach-Object { [pscustomobject]@{"
             "Alias=$_.InterfaceAlias; Index=$_.InterfaceIndex; IP=($_.IPv4Address | Select-Object -First 1).IPAddress; Prefix=($_.IPv4Address | Select-Object -First 1).PrefixLength;"
             "Gateway=($_.IPv4DefaultGateway | Select-Object -First 1).NextHop; Description=$_.NetAdapter.InterfaceDescription; Medium=[string]$_.NetAdapter.PhysicalMediaType } } | ConvertTo-Json -Compress")
PS_NEIGHBOURS = "Get-NetNeighbor -AddressFamily IPv4 -InterfaceIndex {index} | ForEach-Object {{ [pscustomobject]@{{ IP=$_.IPAddress; MAC=$_.LinkLayerAddress; State=[string]$_.State }} }} | ConvertTo-Json -Compress"
REPLY_TIME = re.compile(r"(?:time|temps|zeit|tiempo|tempo|durée)\s*[=<]\s*(\d+)\s*ms", re.I)


def default_run(args: list[str], timeout: float = 20) -> str:
    try:
        done = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return ""
    for encoding in ("utf-8", "cp850", "cp1252"):
        try:
            return done.stdout.decode(encoding)
        except UnicodeDecodeError:
            continue
    return done.stdout.decode("utf-8", errors="replace")


def as_list(text: str) -> list[dict]:
    try:
        data = json.loads(text) if text.strip() else []
    except ValueError:
        return []
    return [d for d in (data if isinstance(data, list) else [data]) if isinstance(d, dict)]


def norm_mac(mac: str) -> str:
    digits = re.sub(r"[^0-9a-fA-F]", "", mac or "").lower()
    return ":".join(digits[i:i + 2] for i in range(0, 12, 2)) if len(digits) == 12 else ""


def randomised(mac: str) -> bool:
    """Phones and tablets often use a made-up hardware address per network; those have this bit set."""
    m = norm_mac(mac)
    return bool(m) and m[1] in "26ae"


def parse_ping(text: str, sent: int) -> dict:
    times = [int(t) for t in REPLY_TIME.findall(text or "")]
    replies = min(len(times), sent)
    return {"sent": sent, "replies": replies, "loss": round(100 * (sent - replies) / sent) if sent else 100, "avg": round(sum(times[:sent]) / replies) if replies else None,
            "worst": max(times[:sent]) if replies else None}


def parse_wlan(text: str) -> dict:
    """`netsh wlan show interfaces`, in English, French, German or Spanish Windows."""
    def find(names: str, pattern: str = r"(.+)"):
        m = re.search(rf"^\s*(?:{names})\s*:\s*{pattern}\s*$", text or "", re.I | re.M)
        return m.group(1).strip() if m else None
    ssid = find(r"SSID")
    signal = find(r"Signal|Señal", r"(\d+)\s*%")
    channel = find(r"Channel|Canal|Kanal", r"(\d+)")
    rx = find(r"Receive rate \(Mbps\)|Réception \(Mbits/s\)|Empfangsrate \(MBit/s\)|Velocidad de recepción \(Mbps\)", r"([\d.,]+)")
    tx = find(r"Transmit rate \(Mbps\)|Transmission \(Mbits/s\)|Übertragungsrate \(MBit/s\)|Velocidad de transmisión \(Mbps\)", r"([\d.,]+)")
    radio = find(r"Radio type|Type de radio|Funktyp|Tipo de radio")
    num = lambda v: float(v.replace(",", ".")) if v else None
    ch = int(channel) if channel else None
    return {"ssid": ssid, "signal": int(signal) if signal else None, "channel": ch, "band": None if ch is None else ("2.4 GHz" if ch <= 14 else "5 GHz"),
            "rx": num(rx), "tx": num(tx), "radio": radio}


def parse_channels(text: str) -> list[int]:
    """The channel of every access point in range, from `netsh wlan show networks mode=bssid`."""
    return [int(c) for c in re.findall(r"^\s*(?:Channel|Canal|Kanal)\s*:\s*(\d+)\s*$", text or "", re.I | re.M)]


def crowding(channel: int | None, channels: list[int]) -> int:
    """How many other access points share (or, on 2.4 GHz, overlap) this channel. The first match is our own."""
    if channel is None:
        return 0
    near = [c for c in channels if (abs(c - channel) <= 2 if channel <= 14 else c == channel)]
    return max(0, len(near) - 1)


class Network:
    def __init__(self, path: Path, run=default_run, resolve=None, throughput=None):
        self.path = Path(path)
        self.run = run
        self.resolve = resolve or self._resolve
        self.throughput = throughput            # function() -> {"down": Mbit/s, "up": Mbit/s, "programs": [names]} or None
        self.lock = threading.Lock()
        self.samples: list[dict] = []           # recent background measurements
        self.last_watch = 0.0
        self.last_alert = 0.0
        self.bad_in_a_row = 0

    # ---- stored state: trusted networks, device names, devices seen ----
    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        for key in ("trusted", "names", "seen"):
            if not isinstance(data.get(key), dict):
                data[key] = {}
        data["watch"] = bool(data.get("watch", False))
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    # ---- reading the system ----
    def interface(self) -> dict | None:
        """The connection in use: its address, the router's address, and whether it is Wi-Fi."""
        for item in as_list(self.run(PS + [PS_CONFIG], 20)):
            try:
                net = ipaddress.ip_network(f"{item['IP']}/{int(item['Prefix'])}", strict=False)
                gateway = ipaddress.ip_address(item["Gateway"])
            except (KeyError, ValueError, TypeError):
                continue
            if not net.is_private:
                continue
            text = f"{item.get('Alias', '')} {item.get('Description', '')} {item.get('Medium', '')}".lower()
            return {"index": int(item["Index"]), "ip": str(item["IP"]), "network": net, "gateway": str(gateway), "alias": item.get("Alias", ""),
                    "wifi": bool(re.search(r"wi-?fi|wireless|wlan|802\.11|sans fil", text))}
        return None

    def neighbours(self, iface: dict) -> list[dict]:
        out, seen = [], set()
        for item in as_list(self.run(PS + [PS_NEIGHBOURS.format(index=iface["index"])], 20)):
            mac, ip = norm_mac(str(item.get("MAC", ""))), str(item.get("IP", ""))
            state = str(item.get("State", "")).lower()
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if (not mac or mac in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00") or mac.startswith("01:00:5e") or addr not in iface["network"]
                    or addr == iface["network"].broadcast_address or state in ("unreachable", "incomplete", "permanent", "0", "1", "6") or mac in seen):
                continue
            seen.add(mac)
            out.append({"ip": ip, "mac": mac})
        return sorted(out, key=lambda d: tuple(int(p) for p in d["ip"].split(".")))

    def gateway_mac(self, iface: dict) -> str:
        self.run(["ping", "-n", "1", "-w", "500", iface["gateway"]], 5)
        return next((d["mac"] for d in self.neighbours(iface) if d["ip"] == iface["gateway"]), "")

    def sweep(self, iface: dict) -> None:
        """Say hello to every address of the home network so that devices show up in the neighbour table. Only small private networks."""
        net = iface["network"]
        if not net.is_private:
            return
        if net.num_addresses > 256:                       # a big network: only the 256 addresses around this PC
            net = ipaddress.ip_network(f"{iface['ip']}/24", strict=False)
        hosts = [str(h) for h in net.hosts() if str(h) != iface["ip"]]
        with ThreadPoolExecutor(max_workers=48) as pool:
            list(pool.map(lambda h: self.run(["ping", "-n", "1", "-w", "350", h], 4), hosts))

    @staticmethod
    def _resolve(ip: str) -> str:
        result = [""]

        def work():
            try:
                result[0] = socket.gethostbyaddr(ip)[0]
            except OSError:
                pass
        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(1.5)
        name = result[0].split(".")[0] if result[0] and not re.fullmatch(r"[\d.]+", result[0]) else ""
        return name[:40]

    def ping(self, host: str, count: int = 5) -> dict:
        return parse_ping(self.run(["ping", "-n", str(count), "-w", "1000", host], count * 2 + 6), count)

    def wifi(self) -> dict:
        return parse_wlan(self.run(["netsh", "wlan", "show", "interfaces"], 10))

    # ---- devices ----
    def trusted(self, gateway_mac: str) -> bool:
        return bool(gateway_mac) and gateway_mac in self.load()["trusted"]

    def trust(self, gateway_mac: str, name: str = "") -> None:
        with self.lock:
            data = self.load()
            data["trusted"][gateway_mac] = {"name": name or "home", "at": int(time.time())}
            self.save(data)

    def scan(self, iface: dict, sweep: bool = True, now: float | None = None) -> dict:
        """The devices on the network, with the ones that were not there at the previous scans marked as new."""
        now = time.time() if now is None else now
        if sweep:
            self.sweep(iface)
        found = self.neighbours(iface)
        with ThreadPoolExecutor(max_workers=16) as pool:
            hosts = list(pool.map(self.resolve, [d["ip"] for d in found]))
        with self.lock:
            data = self.load()
            first_scan = not data["seen"]
            devices = []
            for d, host in zip(found, hosts):
                known = data["seen"].get(d["mac"])
                kind = "router" if d["ip"] == iface["gateway"] else ""
                devices.append({**d, "name": data["names"].get(d["mac"], ""), "host": host or (known or {}).get("host", ""), "router": bool(kind),
                                "random": randomised(d["mac"]), "new": not known and not first_scan, "first": (known or {}).get("first", int(now))})
                data["seen"][d["mac"]] = {"first": (known or {}).get("first", int(now)), "last": int(now), "ip": d["ip"], "host": host or (known or {}).get("host", "")}
            self.save(data)
        return {"devices": devices, "this_pc": iface["ip"], "gateway": iface["gateway"], "at": int(now)}

    def name_device(self, target: str, name: str) -> str:
        name = re.sub(r"\s+", " ", name).strip(" .\"'“”")[:40]
        with self.lock:
            data = self.load()
            mac = norm_mac(target) or next((m for m, d in data["seen"].items() if d.get("ip") == target.strip()), "")
            if not mac or mac not in data["seen"]:
                return "I do not know that device, sir. Ask “what devices are on my wifi” first, then use its address from the list."
            if not name:
                return "What shall I call it, sir?"
            data["names"][mac] = name
            self.save(data)
        return f"Done, sir. {data['seen'][mac].get('ip', 'That device')} is now “{name}”."

    @staticmethod
    def describe(d: dict) -> str:
        label = d["name"] or d["host"] or ("the router" if d["router"] else "phone or tablet (private address)" if d["random"] else "unnamed device")
        if d["router"] and d["name"] == "" and d["host"]:
            label += " (the router)"
        return f"{d['ip']:<15} {label}" + (" — NEW" if d.get("new") else "")

    def devices_text(self, result: dict) -> str:
        devices = result["devices"]
        if not devices:
            return "I could not see any other device on the network, sir. Some routers hide devices from each other (guest networks do)."
        new = [d for d in devices if d.get("new")]
        unnamed = [d for d in devices if not d["name"] and not d["router"]]
        lines = [f"I can see {len(devices)} device{'s' if len(devices) != 1 else ''} on your network besides this PC, sir:"]
        lines += ["• " + self.describe(d) for d in devices]
        if new:
            lines.append(f"{len(new)} of them {'was' if len(new) == 1 else 'were'} not there at my earlier scans.")
        if unnamed:
            lines.append(f"To label one, say for example “name device {unnamed[0]['ip']} Mum's phone”. Devices that are asleep or switched off do not show up.")
        return "\n".join(lines)

    # ---- why is it slow ----
    def measure(self, iface: dict, full: bool = True) -> dict:
        m = {"wifi": iface["wifi"], "gateway": self.ping(iface["gateway"], 5 if full else 3), "internet": self.ping(INTERNET_HOST, 5 if full else 3)}
        if iface["wifi"]:
            m["link"] = self.wifi()
            if full:
                m["crowd"] = crowding(m["link"]["channel"], parse_channels(self.run(["netsh", "wlan", "show", "networks", "mode=bssid"], 15)))
        if self.throughput:
            try:
                m["pc"] = self.throughput()
            except Exception:
                m["pc"] = None
        return m

    @staticmethod
    def findings(m: dict) -> list[tuple[int, str]]:
        """(how much it matters 1-3, sentence), most important first."""
        out: list[tuple[int, str]] = []
        gw, net, link, pc = m["gateway"], m["internet"], m.get("link") or {}, m.get("pc") or {}
        if gw["replies"] == 0:
            out.append((3, "This PC cannot reach the router at all. The Wi-Fi link itself is down or very unstable: move closer, or restart the router."))
        else:
            if gw["loss"] >= 20 or (gw["avg"] or 0) >= 50:
                out.append((3, f"The link between this PC and the router is poor ({gw['loss']}% of test messages lost, {gw['avg']} ms delay; it should be under 10 ms with none lost). "
                               "That points to the Wi-Fi itself: distance, walls, interference, or the router being overloaded."))
            elif gw["loss"] > 0 or (gw["avg"] or 0) >= 20 or (gw["worst"] or 0) >= 100:
                out.append((2, f"The link to the router is uneven ({gw['avg']} ms on average, worst {gw['worst']} ms, {gw['loss']}% lost). Video calls and games will feel it."))
            if net["replies"] == 0:
                out.append((3, "The router answers but the internet does not. The problem is on the router's internet side or at your provider, not in your Wi-Fi."))
            elif gw["loss"] < 20 and (gw["avg"] or 0) < 50 and (net["loss"] >= 20 or (net["avg"] or 0) >= 150):
                out.append((3, f"The router answers quickly but the internet is slow ({net['avg']} ms, {net['loss']}% lost). "
                               "That is usually the internet line itself, or another device using most of it."))
            elif gw["loss"] < 20 and (net["avg"] or 0) >= 80:
                out.append((1, f"The internet delay is a little high ({net['avg']} ms)."))
        if m["wifi"] and link.get("signal") is not None:
            if link["signal"] < 40:
                out.append((3, f"The Wi-Fi signal is weak ({link['signal']}%). Move closer to the router or remove obstacles; under 40% the speed drops sharply."))
            elif link["signal"] < 65:
                out.append((2, f"The Wi-Fi signal is only fair ({link['signal']}%)."))
        if m["wifi"] and link.get("band") == "2.4 GHz":
            out.append((1, f"This PC is on the 2.4 GHz band (channel {link['channel']}), which is slower and more crowded. If your router offers a 5 GHz network, use that one when you are near it."))
        if m.get("crowd", 0) >= 4:
            out.append((2, f"{m['crowd']} neighbouring Wi-Fi networks use the same channel ({link.get('channel')}). Changing the channel in the router settings can help."))
        if link.get("rx") is not None and link["rx"] < 30:
            out.append((2, f"The link speed is low ({link['rx']:.0f} Mbit/s), so the Wi-Fi link caps the speed before the internet line does."))
        if pc and (pc.get("down", 0) >= 8 or pc.get("up", 0) >= 3):
            who = ", ".join(pc.get("programs") or []) or "a program"
            out.append((3, f"This PC itself is using the connection right now ({pc['down']:.1f} Mbit/s down, {pc['up']:.1f} Mbit/s up). Busiest: {who}. "
                           "An upload or a big download here slows everyone else."))
        return sorted(out, key=lambda f: -f[0])

    def diagnose_text(self, m: dict, devices: dict | None = None, gateway: str = "") -> str:
        found = self.findings(m)
        gw, net, link = m["gateway"], m["internet"], m.get("link") or {}
        head = "Here is what I measured, sir:"
        facts = [f"• Router: {gw['avg']} ms, {gw['loss']}% lost" if gw["replies"] else "• Router: no answer",
                 f"• Internet: {net['avg']} ms, {net['loss']}% lost" if net["replies"] else "• Internet: no answer"]
        if m["wifi"] and link.get("signal") is not None:
            facts.append(f"• Wi-Fi: signal {link['signal']}%, {link.get('band') or '?'} channel {link.get('channel')}" + (f", link speed {link['rx']:.0f} Mbit/s" if link.get("rx") else "")
                         + (f", {m['crowd']} other networks on the channel" if "crowd" in m else ""))
        elif not m["wifi"]:
            facts.append("• This PC is connected by cable, not Wi-Fi.")
        if m.get("pc"):
            facts.append(f"• This PC is using {m['pc']['down']:.1f} Mbit/s down and {m['pc']['up']:.1f} Mbit/s up")
        if devices is not None:
            new = [d for d in devices["devices"] if d.get("new")]
            facts.append(f"• Devices on the network: {len(devices['devices'])}" + (f" ({len(new)} new: " + ", ".join(d["name"] or d["host"] or d["ip"] for d in new[:3]) + ")" if new else ""))
        lines = [head] + facts + [""]
        serious = [f for f in found if f[0] >= 2]
        if not found:
            lines.append("Nothing looks wrong from here right now: the link to the router and the internet both answer quickly.")
        else:
            lines.append("Most likely cause:" if serious else "Nothing serious, but:")
            lines += [f"{n}. {text}" for n, (_, text) in enumerate(found[:4], 1)]
        lines.append("")
        lines.append("One limit: a PC cannot see how much data each other device uses, only the router can."
                     + (f" Its own page (usually http://{gateway}) often lists that per device." if gateway else ""))
        return "\n".join(lines)

    # ---- the quiet background check ----
    def watch(self, now: float | None = None) -> str | None:
        """Called often; measures every few minutes. Returns a message when the connection is clearly worse than usual, or when a new device joined."""
        now = time.time() if now is None else now
        data = self.load()
        if not data["watch"] or now - self.last_watch < WATCH_EVERY:
            return None
        self.last_watch = now
        iface = self.interface()
        if not iface:
            return None
        gw_mac = self.gateway_mac(iface)
        if not self.trusted(gw_mac):
            return None
        m = self.measure(iface, full=False)
        delay = m["internet"]["avg"] if m["internet"]["replies"] else 2000
        usual = statistics.median(s["delay"] for s in self.samples) if len(self.samples) >= 3 else None
        bad = m["internet"]["loss"] >= 34 or m["gateway"]["loss"] >= 34 or (usual is not None and delay >= max(150, 3 * usual))
        self.bad_in_a_row = self.bad_in_a_row + 1 if bad else 0
        if not bad:
            self.samples = (self.samples + [{"at": now, "delay": delay}])[-24:]
        scan = self.scan(iface, sweep=False, now=now)
        new = [d for d in scan["devices"] if d.get("new")]
        if self.bad_in_a_row >= 2 and now - self.last_alert >= WATCH_COOLDOWN:
            self.last_alert = now
            self.bad_in_a_row = 0
            full = self.measure(iface, full=True)
            return "Your connection has slowed down, sir.\n" + self.diagnose_text(full, scan, iface["gateway"])
        if new:
            return ("A new device joined your network, sir: " + ", ".join(self.describe(d).replace(" — NEW", "").strip() for d in new[:3])
                    + ". If you do not recognise it, change the Wi-Fi password in the router settings.")
        return None


CLEAN_START = r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?"
NET = r"(?:wi-?fi|network|internet|router|connection|lan|broadband)"
ASK_DEVICES = re.compile(rf"(?:what|which|how\s+many)\s+(?:devices?|things?|gadgets?|computers?|phones?)\s+(?:are|is)\s+(?:connected\s+|hooked\s+up\s+|currently\s+)?(?:on|to|using)\s+(?:my|the|our|this)\s+{NET}"
                         rf"|who(?:'s|\s+is|\s+else\s+is)\s+(?:connected\s+)?(?:on|to|using)\s+(?:my|the|our)\s+{NET}"
                         rf"|(?:scan|list|show(?:\s+me)?|check)\s+(?:the\s+|my\s+|our\s+)?(?:{NET}\s+(?:for\s+)?devices|devices\s+(?:on|connected\s+to)\s+(?:my|the|our)\s+{NET}|{NET}\s+scan)"
                         rf"|(?:scan|map)\s+(?:my|the|our)\s+{NET}|{NET}\s+devices|(?:any|are\s+there(?:\s+any)?)\s+(?:new|unknown|strange)\s+devices?(?:\s+on\s+(?:my|the|our)\s+{NET})?", re.I)
ASK_SLOW = re.compile(rf"why\s+is\s+(?:my|the|our)\s+{NET}\s+(?:so\s+|this\s+|really\s+)?(?:slow|bad|laggy|lagging|terrible|rubbish|unstable|dropping|cutting\s+out)(?:\s+(?:today|right\s+now|again|tonight))?"
                      rf"|(?:my|the|our)\s+{NET}\s+is\s+(?:so\s+|really\s+|very\s+|super\s+)?(?:slow|bad|laggy|lagging|terrible|unstable)(?:\s+(?:today|right\s+now|again))?"
                      rf"|(?:check|test|diagnose|analy[sz]e|troubleshoot)\s+(?:my|the|our)\s+{NET}(?:\s+(?:speed|connection|health|quality))?"
                      rf"|what(?:'s|\s+is)\s+(?:slowing(?:\s+down)?|wrong\s+with|using(?:\s+up)?|hogging|eating)\s+(?:down\s+)?(?:my|the|our)\s+{NET}"
                      rf"|(?:is\s+)?(?:something|anything|someone)\s+(?:slowing(?:\s+down)?|hogging|using(?:\s+up)?)\s+(?:down\s+)?(?:my|the|our)\s+{NET}|{NET}\s+(?:check|health|report|test|diagnosis)", re.I)
YES = re.compile(r"(?:yes|yep|yeah|ok|okay|sure)[,.!]?\s+(?:please\s+)?(?:scan|do\s+the\s+scan|scan\s+(?:it|the\s+network)|it(?:'s|\s+is)\s+(?:my|our)\s+(?:own\s+)?network|go\s+ahead\s+and\s+scan)(?:\s+it)?", re.I)
NAME = re.compile(r"(?:name|call|label|rename)\s+(?:the\s+)?device\s+((?:\d{1,3}\.){3}\d{1,3}|(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2})\s+(?:as\s+|to\s+)?(.+)", re.I)
WATCH_ON = re.compile(rf"(?:watch|monitor|keep\s+an\s+eye\s+on)\s+(?:my|the|our)\s+{NET}|(?:turn|switch)\s+on\s+(?:the\s+)?{NET}\s+(?:watch|monitor(?:ing)?)|tell\s+me\s+when\s+(?:my|the|our)\s+{NET}\s+(?:gets?|is)\s+slow", re.I)
WATCH_OFF = re.compile(rf"(?:stop|don'?t)\s+(?:watching|monitoring|watch|monitor)\s+(?:my|the|our)\s+{NET}|(?:turn|switch)\s+off\s+(?:the\s+)?{NET}\s+(?:watch|monitor(?:ing)?)", re.I)


def command(text: str, net: Network, remote: bool = False, now: float | None = None) -> str | None:
    now = time.time() if now is None else now
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(CLEAN_START, "", t, flags=re.I)
    t = re.sub(r"\s*(?:please|for me|now)?\s*[.!?]*$", "", t, flags=re.I).strip()
    if not t or len(t) > 160:
        return None
    m = NAME.fullmatch(t)
    if m:
        return net.name_device(m.group(1), m.group(2))
    if WATCH_ON.fullmatch(t) or WATCH_OFF.fullmatch(t):
        on = bool(WATCH_ON.fullmatch(t))
        with net.lock:
            data = net.load()
            data["watch"] = on
            net.save(data)
        return ("I will keep an eye on the connection, sir, and tell you when it gets clearly slower than usual or when a new device joins. It only works on a network you have let me scan."
                if on else "I have stopped watching the connection, sir.")
    confirming = bool(YES.fullmatch(t)) and now - PENDING["at"] <= CONFIRM_SECONDS
    if not (ASK_DEVICES.fullmatch(t) or ASK_SLOW.fullmatch(t) or confirming):
        return None
    iface = net.interface()
    if not iface:
        PENDING["at"] = 0.0
        return "This PC does not seem to be on a home network right now, sir, so there is nothing I can check."
    if confirming:
        gw_mac = net.gateway_mac(iface)
        PENDING["at"] = 0.0
        if remote:
            return "Confirm that on the PC itself, sir."
        if not gw_mac or gw_mac != PENDING["gateway"]:
            return "The network changed in the meantime, sir. Ask me again."
        net.trust(gw_mac, (net.wifi().get("ssid") or "") if iface["wifi"] else "")
        return net.devices_text(net.scan(iface, sweep=True, now=now))
    if ASK_SLOW.fullmatch(t):
        gw_mac = net.gateway_mac(iface)
        devices = net.scan(iface, sweep=False, now=now) if net.trusted(gw_mac) else None
        return net.diagnose_text(net.measure(iface, full=True), devices, iface["gateway"])
    gw_mac = net.gateway_mac(iface)
    if not net.trusted(gw_mac):
        if remote:
            return "I have not been told that this network is yours, sir. Ask me at the PC first."
        PENDING.update(at=now, gateway=gw_mac)
        name = (net.wifi().get("ssid") if iface["wifi"] else None) or "this network"
        return (f"I have not scanned “{name}” before, sir. A scan lists the devices of everyone on the network, so I only do it on a network that is yours "
                "(not at school, at work or on public Wi-Fi). If it is your own network, say “yes, scan”.")
    return net.devices_text(net.scan(iface, sweep=True, now=now))
