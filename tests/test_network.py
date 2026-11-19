import json, os, sys, tempfile, threading, time, http.client, importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
tmp=Path(tempfile.mkdtemp())
from testlib import stage; stage(tmp)
sys.path.insert(0,"app")
import network as N
# ---------- reading what Windows prints, in English and in French ----------
WLAN_EN="""
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz
    State                  : connected
    SSID                   : HomeBox-5G
    BSSID                  : a4:91:b1:22:33:44
    Radio type             : 802.11ax
    Channel                : 44
    Receive rate (Mbps)    : 866.7
    Transmit rate (Mbps)   : 866.7
    Signal                 : 82%
"""
WLAN_FR="""
Il existe 1 interface sur le système :

    Nom                    : Wi-Fi
    Description            : Realtek RTL8822CE 802.11ac
    État                   : connecté
    SSID                   : Livebox-A1B2
    BSSID                  : 5c:b1:3e:aa:bb:cc
    Type de radio          : 802.11n
    Canal                  : 6
    Réception (Mbits/s)    : 26
    Transmission (Mbits/s) : 39
    Signal                 : 34%
"""
w=N.parse_wlan(WLAN_EN); assert w=={"ssid":"HomeBox-5G","signal":82,"channel":44,"band":"5 GHz","rx":866.7,"tx":866.7,"radio":"802.11ax"}, w
w=N.parse_wlan(WLAN_FR); assert w["ssid"]=="Livebox-A1B2" and w["signal"]==34 and w["channel"]==6 and w["band"]=="2.4 GHz" and w["rx"]==26.0 and w["radio"]=="802.11n", w
assert N.parse_wlan("")["signal"] is None
NETS="SSID 1 : A\n    BSSID 1 : aa\n         Channel            : 6\nSSID 2 : B\n    BSSID 1 : bb\n         Canal              : 6\n    BSSID 2 : cc\n         Channel            : 4\nSSID 3 : C\n         Channel            : 11\nSSID 4 : D\n         Kanal              : 8\nSSID 5: E\n   Channel : 44\n"
assert N.parse_channels(NETS)==[6,6,4,11,8,44] and N.crowding(6,N.parse_channels(NETS))==3 and N.crowding(44,N.parse_channels(NETS))==0 and N.crowding(None,[6])==0
PING_EN="Pinging 192.168.1.1 with 32 bytes of data:\nReply from 192.168.1.1: bytes=32 time=3ms TTL=64\nReply from 192.168.1.1: bytes=32 time<1ms TTL=64\nRequest timed out.\nReply from 192.168.1.1: bytes=32 time=9ms TTL=64\nReply from 192.168.1.1: bytes=32 time=4ms TTL=64\n"
PING_FR="Envoi d'une requête 'Ping'  1.1.1.1 avec 32 octets de données :\nRéponse de 1.1.1.1 : octets=32 temps=24 ms TTL=57\nRéponse de 1.1.1.1 : octets=32 temps=31 ms TTL=57\nDélai d'attente de la demande dépassé.\n"
assert N.parse_ping(PING_EN,5)=={"sent":5,"replies":4,"loss":20,"avg":4,"worst":9} and N.parse_ping(PING_FR,3)=={"sent":3,"replies":2,"loss":33,"avg":28,"worst":31}
assert N.parse_ping("General failure.",3)=={"sent":3,"replies":0,"loss":100,"avg":None,"worst":None}
assert N.norm_mac("A4-91-B1-22-33-44")=="a4:91:b1:22:33:44" and N.norm_mac("nope")=="" and N.randomised("da:a1:19:00:00:01") and not N.randomised("a4:91:b1:22:33:44")
# ---------- a pretend PC ----------
class PC:
    def __init__(s):
        s.config=[{"Alias":"Wi-Fi","Index":12,"IP":"192.168.1.20","Prefix":24,"Gateway":"192.168.1.1","Description":"Intel(R) Wi-Fi 6 AX201","Medium":"Native 802.11"}]
        s.neigh=[{"IP":"192.168.1.1","MAC":"A4-91-B1-22-33-44","State":"Reachable"},{"IP":"192.168.1.23","MAC":"DA-A1-19-00-00-01","State":"Stale"},{"IP":"192.168.1.30","MAC":"3C-22-FB-10-20-30","State":"Reachable"},
                 {"IP":"192.168.1.255","MAC":"FF-FF-FF-FF-FF-FF","State":"Permanent"},{"IP":"224.0.0.22","MAC":"01-00-5E-00-00-16","State":"Permanent"},{"IP":"192.168.1.77","MAC":"00-00-00-00-00-00","State":"Unreachable"},
                 {"IP":"10.0.0.5","MAC":"AA-BB-CC-00-00-05","State":"Reachable"}]
        s.gw="Reply from x: bytes=32 time=2ms TTL=64\n"*5; s.net="Reply from x: bytes=32 time=18ms TTL=57\n"*5; s.wlan=WLAN_EN; s.nets=NETS; s.pings=[]
    def __call__(s,args,timeout=20):
        if args[0]=="powershell.exe":
            return json.dumps(s.config if len(s.config)!=1 else s.config[0]) if "Get-NetIPConfiguration" in args[-1] else json.dumps(s.neigh)
        if args[0]=="ping":
            s.pings.append(args[-1]); n=int(args[2])
            if n==1: return ""
            return s.gw if args[-1]=="192.168.1.1" else s.net
        if args[:3]==["netsh","wlan","show"]: return s.wlan if args[3]=="interfaces" else s.nets
        return ""
pc=PC(); names={"192.168.1.30":"Living-Room-TV.home"}
net=N.Network(tmp/"net.json",run=pc,resolve=lambda ip:names.get(ip,"").split(".")[0],throughput=lambda:{"down":0.4,"up":0.1,"programs":[]})
iface=net.interface(); assert iface["ip"]=="192.168.1.20" and iface["gateway"]=="192.168.1.1" and iface["wifi"] is True and iface["index"]==12
assert [d["ip"] for d in net.neighbours(iface)]==["192.168.1.1","192.168.1.23","192.168.1.30"], "broadcast, multicast, dead and foreign addresses are left out"
assert net.gateway_mac(iface)=="a4:91:b1:22:33:44"
# ---------- the chat flow: a scan needs "yes, scan" once per network, at the PC ----------
t0=1_800_000_000.0; C=lambda q,remote=False,now=t0: N.command(q,net,remote,now)
for q in ("what is wifi","why is the sky blue","who is on the phone","how does a router work","scan this document","check my email","yes","yes, scan"): assert C(q) is None, q
pc.pings.clear(); r=C("what devices are on my wifi"); assert "I have not scanned “HomeBox-5G” before" in r and "yes, scan" in r and not any(p.endswith(".77") or p.endswith(".100") for p in pc.pings), r
assert "Ask me at the PC first" in C("who is on my network",remote=True)
C("what devices are on my wifi"); assert C("yes, scan",remote=True)=="Confirm that on the PC itself, sir." and C("yes, scan") is None, "a remote yes cancels the request"
C("what devices are on my wifi"); assert C("yes, scan",now=t0+N.CONFIRM_SECONDS+5) is None, "too late"
C("scan my network"); pc.pings.clear(); r=C("Yes, scan")
assert "I can see 3 devices on your network besides this PC" in r and "192.168.1.1" in r and "the router" in r and "Living-Room-TV" in r and "phone or tablet (private address)" in r and "NEW" not in r, r
assert len(set(pc.pings))==253 and "192.168.1.20" not in pc.pings, "every address of the home network except this PC"
assert net.trusted("a4:91:b1:22:33:44") and json.loads((tmp/"net.json").read_text())["trusted"]["a4:91:b1:22:33:44"]["name"]=="HomeBox-5G"
# afterwards no question; a device that appears later is marked
pc.neigh.append({"IP":"192.168.1.41","MAC":"B8-27-EB-01-02-03","State":"Reachable"})
r=C("who's on my wifi"); assert "4 devices" in r and "192.168.1.41" in r and r.count("NEW")==1 and "1 of them was not there" in r, r
assert "NEW" not in C("list devices on my network")
assert C("name device 192.168.1.23 Mum's phone")=="Done, sir. 192.168.1.23 is now “Mum's phone”." and "Mum's phone" in C("what devices are on my wifi") and "do not know that device" in C("name device 192.168.1.99 Ghost")
# a public or foreign network is never scanned
pc.config=[{"Alias":"Wi-Fi","Index":12,"IP":"8.8.4.20","Prefix":24,"Gateway":"8.8.4.1","Description":"x","Medium":"Native 802.11"}]; assert "not seem to be on a home network" in C("what devices are on my wifi")
pc.config=[{"Alias":"Wi-Fi","Index":12,"IP":"192.168.1.20","Prefix":24,"Gateway":"192.168.1.1","Description":"Intel(R) Wi-Fi 6 AX201","Medium":"Native 802.11"}]
# another network (a different router): asks again
old=pc.neigh[0]["MAC"]; pc.neigh[0]["MAC"]="5C-B1-3E-AA-BB-CC"; pc.wlan=WLAN_FR; assert "I have not scanned “Livebox-A1B2” before" in C("what devices are on my wifi"); N.PENDING["at"]=0
# a very large network: only the 254 addresses around this PC
pc.config[0]["Prefix"]=16; net.trust("5c:b1:3e:aa:bb:cc"); pc.pings.clear(); C("scan my network"); assert len(set(pc.pings))==253; pc.config[0]["Prefix"]=24
pc.neigh[0]["MAC"]=old; pc.wlan=WLAN_EN
# ---------- why is it slow ----------
r=C("why is my wifi slow"); assert "Router: 2 ms, 0% lost" in r and "Internet: 18 ms, 0% lost" in r and "signal 82%, 5 GHz channel 44, link speed 867 Mbit/s, 0 other networks" in r and "Devices on the network: 4" in r \
    and "Nothing looks wrong from here" in r and "cannot see how much data each other device uses" in r and "http://192.168.1.1" in r, r
pc.wlan=WLAN_FR; pc.gw=("Reply: time=85ms\n"*3)+"Request timed out.\n"*2
r=C("my wifi is so slow today"); assert "Most likely cause:" in r and "link between this PC and the router is poor (40% of test messages lost, 85 ms" in r and "signal is weak (34%)" in r and "2.4 GHz band (channel 6)" in r and "link speed is low (26 Mbit/s)" in r, r
assert r.index("link between this PC") < r.index("2.4 GHz band"), "the serious things come first"
pc.wlan=WLAN_EN; pc.gw="Reply: time=2ms\n"*5; pc.net="Reply: time=240ms\n"*4+"Request timed out.\n"
r=C("what's slowing down my wifi"); assert "router answers quickly but the internet is slow (240 ms, 20% lost)" in r and "weak" not in r, r
pc.net="Request timed out.\n"*5; assert "The router answers but the internet does not" in C("check my connection")
pc.gw="Request timed out.\n"*5; assert "cannot reach the router at all" in C("wifi report")
pc.gw="Reply: time=2ms\n"*5; pc.net="Reply: time=18ms\n"*5
net.throughput=lambda:{"down":42.5,"up":1.2,"programs":["Steam","chrome"]}; r=C("is something hogging the wifi"); assert "This PC itself is using the connection right now (42.5 Mbit/s down, 1.2 Mbit/s up). Busiest: Steam, chrome" in r, r
def broken(): raise OSError("no counters")
net.throughput=broken; assert "Nothing looks wrong" in C("check my wifi")
net.throughput=lambda:{"down":0.2,"up":0.1,"programs":[]}
pc.config[0].update(Alias="Ethernet",Description="Realtek PCIe GbE",Medium="802.3"); r=C("why is my internet slow"); assert "connected by cable, not Wi-Fi" in r and "signal" not in r; pc.config[0].update(Alias="Wi-Fi",Description="Intel(R) Wi-Fi 6 AX201",Medium="Native 802.11")
# an untrusted network: the measurements still work, but no device list
pc.neigh[0]["MAC"]="11-22-33-44-55-66"; r=C("why is my wifi slow"); assert "Router: 2 ms" in r and "Devices on the network" not in r; pc.neigh[0]["MAC"]=old
# ---------- the quiet background check ----------
assert net.watch(t0) is None, "off by default"
assert "keep an eye" in C("watch my wifi") and net.load()["watch"] is True
t=t0+10
for i in range(4): assert net.watch(t) is None; t+=N.WATCH_EVERY+1
n=len(net.samples); assert n==4 and net.watch(t-5) is None and len(net.samples)==n, "not more often than every five minutes"
pc.net="Reply: time=400ms\n"*3; assert net.watch(t) is None, "one bad reading is not enough"; t+=N.WATCH_EVERY+1
msg=net.watch(t); assert msg and msg.startswith("Your connection has slowed down, sir.") and "internet is slow (400 ms" in msg, msg; t+=N.WATCH_EVERY+1
assert net.watch(t) is None and net.watch(t+N.WATCH_EVERY+1) is None, "then quiet for half an hour"
pc.net="Reply: time=18ms\n"*3; t+=N.WATCH_COOLDOWN
pc.neigh.append({"IP":"192.168.1.66","MAC":"0C-11-22-33-44-55","State":"Reachable"}); msg=net.watch(t); assert msg and msg.startswith("A new device joined your network, sir: 192.168.1.66") and "Wi-Fi password" in msg, msg
t+=N.WATCH_EVERY+1; assert net.watch(t) is None, "each new device is announced once"
pc.neigh[0]["MAC"]="11-22-33-44-55-66"; t+=N.WATCH_EVERY+1; pc.net="Reply: time=900ms\n"*3; assert net.watch(t) is None and net.watch(t+N.WATCH_EVERY+1) is None, "never on a network that is not yours"; pc.neigh[0]["MAC"]=old
assert "stopped watching" in C("stop watching my wifi") and net.load()["watch"] is False
# ---------- in the server ----------
spec=importlib.util.spec_from_file_location("srv","app/server.py"); S=importlib.util.module_from_spec(spec); spec.loader.exec_module(S); S.ROOT=tmp
pc2=PC(); net2=N.Network(tmp/"data"/"network.json",run=pc2,resolve=lambda ip:"",throughput=lambda:{"down":0.1,"up":0.1,"programs":[]}); S.network_obj=lambda: net2; N.PENDING["at"]=0
app=ThreadingHTTPServer(("127.0.0.1",0),S.Handler); threading.Thread(target=app.serve_forever,daemon=True).start(); port=app.server_address[1]
def call(m,path,body=None):
    c=http.client.HTTPConnection("127.0.0.1",port); c.request(m,path,json.dumps(body) if body is not None else None,{"Content-Type":"application/json"}); r=c.getresponse(); return r.status,json.loads(r.read())
def chat(text,source=None):
    body={"messages":[{"role":"user","content":text}],"stream":False}
    if source: body["source"]=source
    return call("POST","/api/chat",body)[1]
assert "Ask me at the PC first" in chat("what devices are on my wifi","telegram")["reply"]
assert "yes, scan" in chat("what devices are on my wifi")["reply"]; d=chat("yes, scan"); assert "3 devices" in d["reply"], d
assert "3 devices" in chat("who is on my network","telegram")["reply"], "once it is known as yours, the list can be read from the phone"
assert "Nothing looks wrong" in chat("why is my wifi slow")["reply"]
S.ai_translate=lambda t,c:"[fr] "+t; assert chat("pourquoi le wifi est si lent ?")["reply"].startswith("[fr] Here is what I measured") and "3 devices" in chat("quels appareils sont connectés au wifi")["reply"]
s,d=call("GET","/api/network"); assert d=={"watch":False,"trusted":1,"known_devices":3}
events=[]; S.publish_event=lambda e:events.append(e)
S.network_watch_in_background(); time.sleep(0.3); assert events==[] and net2.last_watch==0, "off: nothing is measured"
s,d=call("POST","/api/network",{"watch":True}); assert d=={"watch":True}
pc2.neigh.append({"IP":"192.168.1.88","MAC":"0C-AA-BB-CC-DD-EE","State":"Reachable"}); S.network_watch_in_background(); time.sleep(1.0)
assert len(events)==1 and events[0]["type"]=="proactive" and "new device joined" in events[0]["text"] and events[0]["speak"] is False, events
tools=S.router_registry().tools; assert "wifi_check" in tools and tools["wifi_devices"].remote is False
# ---------- settings page ----------
pc2.neigh[0]["MAC"]="77-88-99-AA-BB-CC"      # a network Jarvis has not seen
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b=pw.chromium.launch(); pg=b.new_context(viewport={"width":1280,"height":900}).new_page(); errs=[]
    pg.on("pageerror",lambda e:errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{port}/"); pg.evaluate("localStorage.setItem('jarvis-boot-mode','never');localStorage.setItem('jarvis-brief-mode','off')"); pg.reload(); pg.wait_for_timeout(400)
    pg.click("button:has-text('Settings') >> nth=0"); pg.click("#tab-pc")
    pg.wait_for_function("document.querySelector('#net-watch').checked",timeout=8000)
    pg.click("#net-check"); pg.wait_for_function("document.querySelector('#net-report').textContent.includes('Router: 2 ms') && !document.querySelector('#net-check').disabled",timeout=15000)
    assert pg.is_hidden("#net-mine")
    pg.click("#net-devices"); pg.wait_for_function("document.querySelector('#net-report').textContent.includes('has not scanned') && !document.querySelector('#net-mine').hidden",timeout=15000)
    pg.click("#net-mine"); pg.wait_for_function("document.querySelector('#net-report').textContent.includes('devices on your network') && document.querySelector('#net-mine').hidden",timeout=15000)
    assert net2.trusted("77:88:99:aa:bb:cc")
    pg.uncheck("#net-watch"); pg.wait_for_timeout(500); assert net2.load()["watch"] is False and not errs, errs
    pg.keyboard.press("Escape"); pg.keyboard.press("Control+k"); pg.keyboard.type("who is connected")
    pg.wait_for_function("[...document.querySelectorAll('#pane-timers .settings-section')].some(s=>!s.hidden && s.offsetParent && s.textContent.includes('Wi-Fi and network'))",timeout=8000)
    b.close()
print("network ok"); os._exit(0)
