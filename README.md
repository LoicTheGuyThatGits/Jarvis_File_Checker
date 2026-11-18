# Jarvis

A small Windows desktop assistant with a local web chat, push-to-talk input, cloud AI, local browser history, and approval gated actions.

Source: <https://github.com/LoicTheGuyThatGits/Jarvis_File_Checker> · Licence: [MIT](LICENSE)

## Easiest setup (Windows)

1. Double-click `install-jarvis.bat` once. It checks for Python 3.10 or newer (and offers to install it with winget), creates a private environment in the `.venv` folder in the Jarvis folder, and installs PyAutoGUI, Pillow and psutil into it. Nothing is installed system-wide. If Ollama is present it can also download the `llama3.2:3b` model.
2. Double-click `start-jarvis.bat` whenever you want to use Jarvis. It uses the `.venv` environment automatically.

The `.venv` folder is tied to this PC. If you copy Jarvis to another computer, copy everything except `.venv` and run `install-jarvis.bat` there. The manual steps below do the same thing by hand.

## Missing files, updates and a new computer
`filecheck.py` (in the Jarvis folder) compares your folder with the list of files in the GitHub repository (`manifest.json`) and tells you exactly which are missing or different. It uses only Python, so it works even when the rest of Jarvis is broken.

- **In Jarvis:** Settings > Daily > **File check**, or say "check my files". It lists what is missing and asks before downloading; say "yes, restore them" (or press the button). Only at the PC, never from Telegram.
- **Without Jarvis:** double-click `repair-jarvis.bat`, or run `python filecheck.py` (check only), `python filecheck.py --repair` (download the missing files after asking), `python filecheck.py --repair --all` (also replace files that differ; the old copy goes to `data/file-backups`).
- **Safety:** every download is checked against the SHA-256 fingerprint in `manifest.json` before it is written. Your `data` folder (settings, passwords, tokens), `.venv` and `model` are never read or changed. Files you edited yourself are only replaced when you ask for it with `--all` or the checkbox.
- **Updates:** say "check for updates" (or Settings > Daily > File check > **Check for updates**). Jarvis lists new files and files the repository changed, and installs them after you say "yes, update" (or press **Install updates**). Files you changed yourself are left alone unless you tick the "also replace changed files" box; the old copy always goes to `data/file-backups`. From the command line: `python filecheck.py --update` (add `--all` to also replace changed files). Jarvis also checks quietly about every 12 hours and tells you once in the chat when something new is available; untick "Tell me when the repository has an update" to stop that. Restart Jarvis after an update.
- **Pin a version:** `python filecheck.py --ref v1.0` uses a release tag instead of the `main` branch. To make it permanent, put `{"ref": "v1.0"}` in `data/filecheck.json`.
- **Offline:** if GitHub cannot be reached, the `manifest.json` in your folder is used to list what is missing (nothing can be downloaded then).

**New computer:** install Python 3.10 or newer, make a folder (for example `C:\Jarvis`), open PowerShell in it and run:

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/LoicTheGuyThatGits/Jarvis_File_Checker/main/filecheck.py -OutFile filecheck.py
python filecheck.py --repair
```

It downloads every file, then run `install-jarvis.bat` as described above. Your own settings and keys are not in the repository; set them up again on that computer.

**For the repository owner:** after changing any file run `python tools/make_manifest.py` to refresh `manifest.json` (a GitHub Action in `.github/workflows/manifest.yml` also does it on every push), and `python tools/make_manifest.py --check` to see whether it is up to date. The script refuses to continue if a listed file seems to contain a Telegram token, an API key or a login token. `.gitignore` keeps `data/`, `.venv/`, `model/` and build files out of the repository, so run `git status` before the first push and check that none of them is listed.

## What Jarvis calls you

The installer asks whether Jarvis should call you “sir”, “ma'am” or a name you type. The choice is saved in `data/address.txt`. To change it later, run the installer again, run `py app/set-address.py`, or edit `data/address.txt` (reload the page afterwards). `JARVIS_ADDRESS` overrides the file.

## Folder layout

```
Jarvis/
  install-jarvis.bat       run once to set everything up
  start-jarvis-app.bat     start Jarvis as an app (tray icon, own window, hotkey)
  start-jarvis.bat         start Jarvis in a console window instead
  build-jarvis-model.bat   build the local "jarvis" model in Ollama from model\Modelfile
  app/                     the program: server.py, telegram_bot.py, jarvis_tray.py, jarvis_window.py, set-address.py
  web/                     the page: index.html, css/, js/, icons/
  data/                    your saved data: settings, memory, reminders, routines, documents,
                           address.txt, logs and the app window's browser profile
  model/                   your Modelfile (the recipe for the "jarvis" model); updates never touch it
  piper/                   optional offline voices
  .venv/                   private Python environment (made by the installer, specific to this PC)
```

To share Jarvis, give someone everything except `.venv` and `data`. Older versions kept these files next to `server.py`; Jarvis moves them into `data/` the first time it starts.

## Jarvis on Android

The `android` folder holds a phone version of Jarvis (a Cordova project). A ready-built test app is `android/Jarvis-debug.apk`: copy it to the phone and open it to install (Android asks you to allow installing from that source). To rebuild after changing anything in `android/www`, run `cordova build android` in the `android` folder; it needs the Cordova command line, a JDK and the Android SDK.

The app has four tabs (Chat, Planner, PC, Settings) and three brains, chosen in **Settings > Brain**:

- **Ollama**: a model running on the phone itself in Termux, or on any Ollama server the phone can reach. In Termux run `pkg install ollama`, then `ollama serve`, and in a second session `ollama pull llama3.2:3b`. Keep Termux open while you chat. The default address is `http://127.0.0.1:11434`.
- **Cloud**: any OpenAI compatible provider. The API key is stored only in the app on the phone.
- **PC**: Jarvis on your PC does the thinking, so opening apps, routines, mail, PC documents and approval cards work from the phone.

With the Ollama or cloud brain the app works without the PC: chat, voice input and spoken replies, timers, reminders and alarms (as Android notifications, even when the app is closed), the to-do list, the calendar, long-term memory, text documents, the ten themes and the startup sequence. Mail and PDF/Word/Excel documents need the PC brain.

**Linking the phone to the PC**: on the PC open **Settings > Daily > Phone app**, tick the box and restart Jarvis (Windows may ask to allow it through the firewall: choose private networks). Enter the address and pairing code shown there in the app under **Settings > PC link**. The PC tab then has power and volume buttons (lock, sleep, restart, shut down, each with a confirmation), a view-only live picture of the PC screen, and buttons for new mail and the briefing. While the phone link is on, Jarvis listens on your local network and anyone on it with the pairing code can control the PC; the connection is not encrypted, so use it only on a network you trust. It is off by default, and the setting is saved in `data/phone.json`.

## Start Jarvis

1. Install Python 3.10 or newer if needed.
2. Install the optional mouse and screen-control packages:

   ```powershell
   py -m pip install -r requirements.txt
   ```

3. In PowerShell, set your OpenAI API key for this terminal session:

   ```powershell
   $env:OPENAI_API_KEY = "your-api-key"
   ```

4. Start the app from this folder:

   ```powershell
   py app/server.py
   ```

Jarvis opens at `http://127.0.0.1:8765`. It listens only on this PC. Close the terminal window to stop it. The key stays on the server and is not sent to the browser.

To use another OpenAI compatible Chat Completions provider, set `OPENAI_BASE_URL` and `OPENAI_MODEL` before starting. Defaults are `https://api.openai.com/v1` and `gpt-6-luna`, a cost efficient OpenAI model for focused tasks. Check current model availability and pricing in the [OpenAI model catalog](https://developers.openai.com/api/docs/models).

## Included in version one

- Streaming replies: chat answers appear word by word as the model writes them, instead of all at once. Computer mode and the instant `open <app>` and file-search shortcuts are unchanged.
- Interface styles and a cosmetic startup sequence: click **Settings** in the top bar to pick one of ten styles (Arc Reactor, Mark III, Crimson, Amber CRT, Toxic, Emerald, Midnight, Nebula, Sakura or Stealth), and to choose whether the startup animation plays on the first launch only, every time Jarvis starts, or never (with a replay button). Choices are saved in this browser, so they survive stopping and restarting the server. Keep the same `JARVIS_PORT`: browsers store settings per address, so a different port starts fresh. Keep the folders `app`, `web` and `data` together (see “Folder layout”).
- Chat search and export: the sidebar search box filters your chats by title and message text and shows the matching line. **Settings > Chats** exports the current chat as Markdown, exports every chat as JSON, and imports a JSON export (it adds chats and never replaces existing ones).
- Voice replies: switch on **♪ Voice** in the top bar and Jarvis speaks each answer as it is written, sentence by sentence, using your browser's voices. It prefers a British male voice and starts with a calm, slightly lower delivery, plus a soft two-note chirp before it speaks (optional). **Settings > Voice** has a **Use the Jarvis voice settings** button, a voice picker, speed and pitch. For the most Jarvis-like sound use Microsoft Edge and pick “Microsoft Ryan Online (Natural) – English (United Kingdom)”. The AI is also told to answer in the calm, dry, polite manner of the film character. Code is never read aloud, the reactor pulses while Jarvis talks, and pressing Stop or sending a new message silences it.
- Web research: say **search the internet for…**, **look up…**, **research…** or **find out…** and Jarvis searches the web, reads the top pages, and answers with numbered marks such as [1] that match the clickable **Sources** under the reply. Asking a question and then saying **look it up** works too. Naming a site (**search YouTube for…**) or saying **google…** still opens the browser instead. Only the search words and the page requests leave the PC; no key or account is needed.
- Proactive Jarvis (**Settings > Planner > Proactive Jarvis**): Jarvis speaks first when something needs your attention. It watches planner events and tasks, new email (the model judges whether it is worth an interruption), PC health (low battery, memory nearly full, a hot graphics card, a nearly full disk) and things finishing (a browser download, or heavy work that kept the PC busy for minutes). It tells you in the chat, aloud when voice is on, as a Windows notification when Jarvis is not the window in front, and on Telegram only when the keyboard and mouse have been untouched for 3 minutes. By default it interrupts at most 4 times an hour and stays silent from 22:00 to 08:00. Say **not now** (or press the button under its message) to hold everything that is not urgent for an hour, **do not disturb for two hours**, or **you can interrupt me again**. An event about to start and a nearly empty battery always get through; what is held is given together afterwards.
- Training log (**Settings > AI model > Training log**): each answer from the chat model is saved in `data/training/` with the prompt that produced it, and 👍 / 👎 under an answer mark the ones worth learning from. `export-training.bat` writes the 👍 answers to `data/training/jarvis-finetune.jsonl`, ready for fine-tuning a model made just to be Jarvis. Everything stays on this PC. A progress bar under it shows how many 👍 answers you have against rough goals: about 50 to check the pipeline, 300 to fix tone and style, 800 to teach Jarvis' habits and commands, 3000 for broad improvement. Quality beats count: varied requests, strict ratings (only 👍 answers that are right), and hand-corrected answers help most. The log holds your real messages, so read the exported file before sharing it.
- Model switcher: click the model name in the top bar (or **Settings > AI model**) to switch between a **Local** model server such as Ollama and a **Cloud** provider, and to pick any installed or available model. The choice applies to your next message and is remembered in `data/settings.json`; delete that file to go back to the launcher's defaults.
- Startup briefing: when Jarvis opens (each start, or once a day; set it in **Settings > Daily**) it shows, and reads aloud if voice replies are on, a short briefing: greeting, time and date, the weather for your location (Laconnex by default, change it in the same tab), your active timers and reminders, and a system check. The weather comes from Open-Meteo and needs an internet connection; without it that line is skipped. You can also say “brief me” or “what's the weather”. In another language the briefing is translated by your AI model.
- Saved routines: in **Settings > Daily > Routines** build a routine from steps (open an app, website or folder, show the desktop, close an app, tell Jarvis something such as “set an alarm for 7am”, say something, volume up or down, wait, give the briefing, run a PowerShell command). Then say its name (“good night”), “run good night”, or any extra phrase you added, or press Run. Jarvis shows the steps and waits for your approval, unless you tick “Run without asking first”. With that ticked every step runs at once, including closing apps and PowerShell commands, so only use it for routines you trust (Jarvis asks you to confirm when you save one like that). Folder steps take a name like `Downloads`, `Documents` or `Desktop`, `~/Work`, or a full path; only existing folders are opened. Routines are saved in `data/routines.json`. Closing an app only asks it to close politely, and volume steps are about 2 percent each.
- Document and file chat: click **+** next to the microphone (or drop files onto the chat, or use **Settings > Memory > Documents**) to add PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), CSV, text, Markdown, JSON, HTML and code files. Switch **Docs on** and ask questions such as “what is the refund window in the policy?” or “how many Widgets shipped in Nord?”. Everything is read on this PC: Jarvis splits each file into passages, finds the few that match your question, and sends only those to your local Ollama model, even if cloud is your normal provider, so nothing goes to a cloud service. Answers cite where they came from (file, page, sheet and rows), and say so when nothing matches instead of guessing. Excel files are read sheet by sheet with the column headers repeated, dates shown as dates. Limits: 25 MB per file, 50 documents, scanned PDFs without a text layer cannot be read, and old .xls/.doc/.ppt files must be re-saved as .xlsx/.docx/.pptx. A small local model is only as good as its context window, so ask specific questions rather than “summarise everything”. Documents are stored in `data/documents`. PDF support needs the `pypdf` package: run `.venv\Scripts\pip install -r requirements.txt` once after updating.
- Jarvis as an app: double-click **start-jarvis-app.bat** (instead of start-jarvis.bat). It starts the server in the background with no console window, opens Jarvis in its own tabless window (Edge, or Chrome if Edge is missing) and puts an icon in the system tray. Closing the window leaves Jarvis running; press **Ctrl+Alt+J** (or double-click the tray icon) to bring it back, and press it again while Jarvis is in front to minimise it. Set `JARVIS_HOTKEY` (for example `ctrl+shift+j`) to change the hotkey. The tray menu has Open, Restart, **Keep PC awake**, **Start with Windows** and Quit; the installer also asks about starting with Windows, and you can run `.venv\Scripts\python.exe app\jarvis_tray.py --autostart on` or `off` yourself. When it starts with Windows, Jarvis waits in the tray (no window) until you open it. The app window uses its own browser profile in `data/app-profile`, so its chats and settings are kept separately, microphone permission is remembered (click Allow the first time if asked), and voice replies and the startup briefing can play without a click. To keep your normal browser profile instead, set `JARVIS_APP_PROFILE=default`. While **Autopilot** runs a computer task, the Jarvis window minimises itself so the screenshots show your real screen, then comes back when the task ends. Voice input still listens only while the window is open (minimised is fine). The server's messages go to `data/jarvis.log`. **Keep PC awake** asks Windows not to go to sleep by itself while Jarvis runs (the screen can still turn off and lock), so Telegram keeps working while you are away; your choice is remembered in `data/tray.json`. If the server ever stops, the tray app restarts it. Jarvis writes a dated line to the log whenever it presses keys or acts on the desktop (volume, mute, show the desktop, bringing its window forward, computer control), so you can check whether it was responsible when the screen wakes. Jarvis starts when you sign in to Windows, not before: a program that runs before sign-in cannot reach your desktop, so desktop commands would silently do nothing. If you want it ready after a restart without typing a password, use Windows' automatic sign-in (run `netplwiz`), which is a security trade-off for your own decision.
- Telegram: talk to Jarvis from your phone. Create a bot by messaging `@BotFather` in Telegram (send `/newbot`, pick a name and a username ending in `bot`) and copy the token. In Jarvis open **Settings > Daily > Telegram**, paste the token, press **Connect**, then send the 6-digit pairing code shown there to your bot. After that Jarvis answers your messages with everything the app can do: timers, memory, the weather, saved routines and chat about your documents (`/docs on`). Send the bot a PDF, Word, Excel or text file to add it to your documents. Timers and reminders are also sent to your phone, and you can ask for the briefing at a fixed time each day. Anything that changes your PC (running a command, saving files, a routine) comes with an Approve and Dismiss button and only happens when you tap Approve; routines set to run without asking still ask when started from the phone. Only the paired account is answered. Jarvis reads messages from Telegram while it is running, so no port needs opening, but it only answers while the PC is on. The token is stored in `data/telegram.json`; keep that file private, and if the token leaks, create a new one with BotFather (`/revoke`) and paste it in again. **Voice notes**: send a voice message and Jarvis transcribes it on your PC with Whisper (free, offline; installed by install-jarvis.bat as `faster-whisper`; the first one downloads a 140 MB speech model, so it is slow once), shows you what it heard, then answers as if you had typed it. It detects the language by itself. Set `JARVIS_WHISPER_MODEL` to `tiny` (faster), `small` or `medium` (more accurate) to change the model. If you chose the cloud provider and faster-whisper is missing, the cloud speech service is used instead. **Photos**: send a photo (or an image file) and add a question as the caption, for example “what does this sign say?” or “what is this plant?”; with no caption Jarvis describes it. This needs a vision model in Ollama, which install-jarvis.bat offers to download and Jarvis finds by itself; if you skipped it, run `ollama pull moondream` (about 1.7 GB, light enough for a PC with little free memory; it describes pictures well but reads small text poorly). With more memory free, `ollama pull gemma3:4b` (about 3.3 GB) is better at reading text and answering questions. Set `JARVIS_LOCAL_VISION_MODEL` to force one. Local vision models are slow on a PC without a graphics card, so allow a minute or two. With the cloud provider the photo is sent to that service.
- Quick PC commands: say or type (or send from Telegram) “show the desktop”, “minimize all windows”, “turn the volume up” (or “volume down by 20”, “louder”, “quieter”), “mute” or “unmute”, or “lock the computer”, and Jarvis does it at once on the PC. “Close Chrome”, “quit Spotify” or “close the calculator app” closes that app: Jarvis asks its windows to close the way the X button does, so an app with unsaved work shows its own “save changes?” prompt and Jarvis tells you it is still open (a screenshot follows from Telegram so you can see it). It never force-kills anything, and it will not close Jarvis itself, File Explorer or the terminal. They only run when the whole message is such a request. Other actions from Telegram, such as running a PowerShell command, still wait for your Approve tap. Say “take a screenshot” or “show me my screen” (or send `/screenshot` on Telegram) to see the screen. From Telegram, Jarvis also sends a screenshot after “show the desktop” and after opening an app or website, so you can see the result; untick this in **Settings > Daily > Telegram** if you would rather not. Screenshots sent to Telegram pass through Telegram's servers and are not end-to-end encrypted, so avoid it when private things are on screen. If the screen is locked or the screenshot fails, Jarvis says so.
- Languages: pick one of 23 languages in **Settings > Voice > Language**, or just say or type “switch to French” (also “speak German”, “go back to English”). Jarvis then replies in that language, listens for it with the microphone, and speaks with a matching voice (for Piper, add a voice whose file name starts with the language code, such as `fr_FR-siwis-medium.onnx`). Menus and built-in messages such as timer alerts stay in English. The choice is saved in `data/settings.json`; `JARVIS_LANGUAGE` overrides it.
- Natural voices: in **Settings > Voice** pick a voice engine. *Browser voice* is the built-in default. *Natural voice (cloud AI)* uses your cloud API key and the `/audio/speech` endpoint (set `JARVIS_TTS_MODEL` to change the model; default `gpt-4o-mini-tts`; speech may incur charges). *Natural voice (offline, Piper)* runs on this PC: download Piper for Windows and a voice such as `en_GB-alan-medium` (the `.onnx` and `.onnx.json` files) and put the voice files in a folder named `piper` in the Jarvis folder, and either put `piper.exe` there too or install Piper with `.venv\\Scripts\\pip install piper-tts` (Jarvis finds it in the `.venv` folder). If a natural voice fails, Jarvis falls back to the browser voice.
- Live system charts: the sidebar shows scrolling Task Manager style charts for CPU, memory and, on NVIDIA cards, GPU load and VRAM, updated every second, plus the battery level. The charts use your theme colors and turn to the thinking color while Jarvis thinks. Click any chart (or **Settings > Look > Open the system monitor**) for a larger monitor with two minutes of history, disk and network throughput, per-thread CPU bars, process count and uptime. Install `psutil` for the full set (`py -m pip install -r requirements.txt`); without it Jarvis falls back to basic Windows readings for CPU, memory and battery only. CPU and GPU charts auto-zoom (10%, 20%, 30%, 50%, 75% or 100% full scale, shown in the chart corner) so small changes stay visible; switch to a fixed 0–100% scale in **Settings > Look > Chart scale**. Memory and VRAM always use 0–100%, so they move slowly. Turn the sidebar charts off in **Settings > Look**.
- Long-term memory: say “remember that my printer is the HP in the office”, “what do you remember?” or “forget the printer”. You can also add, remove and clear memories in **Settings > Memory**. They are kept in `data/memory.json` in the Jarvis folder (up to 100, 300 characters each) and the newest ones are sent with every request, so keep them short.
- Timers and reminders: say “set a timer for 10 minutes”, “set a 25 minute timer called pomodoro”, “remind me in 20 minutes to check the oven”, “remind me tomorrow at 9am to send the report”, “set an alarm for 7am”, “what timers do I have?” or “cancel my timer”. They are handled instantly without the AI. A countdown chip appears in the top bar, and when one comes due Jarvis shows an alert card, rings, flashes the tab title, speaks the message if voice is on, and (if you allow it) sends a desktop notification. Alerts arrive in any open Jarvis tab, even in the background; ones that came due while Jarvis was closed show when you reopen it. Times are stored in `data/reminders.json` and survive restarts. Jarvis must be running (the black window open) for alerts to fire.
- Text chat and browser push-to-talk (speech recognition support varies by browser; current Chrome or Edge is recommended).
- While Jarvis is responding, the send control changes to **Stop**. It cancels the active chat generation; in Autopilot it also requests the computer task stop.
- Multiple conversations saved in this browser's local storage, with controls to start a new chat, switch between saved chats, or clear the current chat.
- Short-term memory: Jarvis uses recent text messages from the current saved chat to understand follow-ups such as “continue that task.” This context stays in this browser's local storage and is sent to the AI provider with a new request; screenshots are not added to chat history.
- Web search and site shortcuts (no AI call, no approval): say “search for cats”, “google how to boil an egg”, “search youtube for lofi music”, “open Chrome and search for cats”, “go to the BBC website”, or “open stackoverflow”. Known sites open directly; an unknown site name jumps to its top search result. If you name Chrome, Edge or Firefox, Jarvis uses it, otherwise your default browser opens. The AI can also run a `web_search` action for less direct wording.
- Explicit `open <app name>` requests and `open_app` proposals search Windows Start and press Enter to launch the top result, without an approval card. This supports apps installed on the PC, including Microsoft Store. Website opens continue to use the browser; other AI-proposed actions continue to require approval.
- Code in any language: ask for code in Python, JavaScript, TypeScript, HTML, CSS, C, C++, C#, Java, Go, Rust, SQL, PowerShell, Bash and many more. Code appears in the chat as formatted blocks with **Copy** and **Download** buttons. To create files, say for example “write a Python calculator and save it as calculator.py” or “build me a small website”: Jarvis can prepare one file or a whole project (up to 12 files, with subfolders such as `css/style.css`). You review each file in an approval card, and after you click **Save**, the files go in the local `workspace` folder (several files go together in a new `project-…` folder). Files are never run automatically, and nothing is overwritten: an existing name gets a number, like `calculator (2).py`.
- Local file search: ask “find files named report” or “search my files for budget.xlsx”. Jarvis searches filenames in Desktop, Documents, Downloads, Pictures, Videos, Music, and the Jarvis project folder, then shows matching paths in chat. It does not read or upload file contents. Search stops after 8 seconds, 100,000 filenames, or 40 results; add more of the filename to narrow results.
- Image generation from a text prompt using local ComfyUI by default. Jarvis asks for approval before generation; generated PNGs can be downloaded. OpenAI image generation remains available by selecting the `openai` image backend.
- Computer mode: Jarvis can inspect the live local screen preview and control the mouse and keyboard. By default, each action needs your approval, with a 12-step task limit. Optional Autopilot runs without step-by-step approvals, stops after 30 actions, and can be stopped with the **Stop** button or global **Ctrl+Shift+F10** shortcut.
- PowerShell commands can be proposed, displayed in full, and run only after you click **Approve and run** and confirm the browser prompt. Commands have a 30 second timeout.

The chat AI receives the recent conversation when you send a message. In computer mode, a resized screenshot of your active desktop is sent to the configured AI provider for visual analysis, so computer tasks use API credits and screen contents leave the PC. History remains in browser storage on this PC. The app does not save the API key to disk. Local ComfyUI image requests run on this PC; the chat still uses the configured cloud AI provider.

To use computer mode, install the packages above, start Jarvis, click **Computer off** in the message bar, and describe one task. The button changes to **Computer on** and shows a local preview. Frames are sent to the AI provider when a task is analyzed and as it runs, so API charges may apply and screen contents leave the PC. Turn on **Autopilot** only for tasks you want carried out without per-step approval. Stay nearby; use **Stop** or press **Ctrl+Shift+F10** to prevent the next action. A currently executing click or keystroke is not undone. Move the mouse to the top-left screen corner to trigger PyAutoGUI's emergency fail-safe if an action is in progress.

## Connect local ComfyUI for free image generation

1. Download and install [Comfy Desktop](https://comfy.org/download), then launch it and create a local install. The desktop app runs the ComfyUI engine on your PC.
2. In ComfyUI, install or download a local text-to-image checkpoint that works with `CheckpointLoaderSimple`. Do not choose a Partner API or cloud workflow if you want image generation to stay local.
3. Keep ComfyUI running while Jarvis is running. Jarvis sends approved image requests to the local ComfyUI server at `http://127.0.0.1:8000` by default.

If ComfyUI shows a different local address, set `JARVIS_COMFY_URL` in your user environment variables to that address (for example `http://127.0.0.1:8188`), then restart Jarvis. To choose a specific installed checkpoint, set `JARVIS_COMFY_MODEL` to its exact filename. If unset, Jarvis uses the first available checkpoint.

Local image generation does not use OpenAI image credits, but it uses your PC's compute and disk space. Jarvis text chat still uses the cloud API and its separate billing. For local image requests, Jarvis does not need an OpenAI API key; chat still does.

## Settings

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | none | Required provider key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI compatible API base URL |
| `OPENAI_MODEL` | `gpt-6-luna` | Chat model name |
| `JARVIS_IMAGE_BACKEND` | `comfyui` | Image backend: `comfyui` or `openai` |
| `JARVIS_COMFY_URL` | `http://127.0.0.1:8000` | Local ComfyUI server address |
| `JARVIS_COMFY_MODEL` | first installed checkpoint | Optional ComfyUI checkpoint filename |
| `JARVIS_IMAGE_MODEL` | `gpt-image-2.5-flare` | OpenAI image model when backend is `openai` |
| `JARVIS_PORT` | `8765` | Local web port |
| `JARVIS_PROVIDER` | `local` if a local server is configured, otherwise `cloud` | Which provider to start on: `local` or `cloud` |
| `JARVIS_LOCAL_BASE_URL` | `http://127.0.0.1:11434/v1` | Local OpenAI compatible server (Ollama) |
| `JARVIS_LOCAL_MODEL` | `llama3.2:3b` | Starting local model |
| `JARVIS_CLOUD_API_KEY` | `OPENAI_API_KEY` | Key for the cloud provider |
| `JARVIS_CLOUD_BASE_URL` | `https://api.openai.com/v1` | Cloud provider address |
| `JARVIS_CLOUD_MODEL` | `gpt-6-luna` | Starting cloud model |
| `JARVIS_VISION_PROVIDER` | the active provider | Set to `cloud` to keep computer mode on the cloud while chat runs locally |

`OPENAI_BASE_URL`, `OPENAI_API_KEY` and `OPENAI_MODEL` still work: an `OPENAI_BASE_URL` that points at this PC is treated as the local server, and anything else as the cloud provider.
| `JARVIS_ANSWER_STYLE` | `developed` | Answer length: `short`, `developed` or `detailed` |

To use paid OpenAI image generation instead, set `JARVIS_IMAGE_BACKEND=openai`. Its requests use the same OpenAI API key and API billing account as chat and can incur API charges. See the [image generation guide](https://developers.openai.com/api/docs/guides/tools-image-generation).

## Coding help

Code in Jarvis's answers is colour-highlighted, with Copy and Download buttons. A block of **HTML, SVG or JavaScript** also gets a **Preview** button: the page or script runs right under the code, so you can try a web page, a small game or an animation without saving anything. If the answer has a `style.css` and a `script.js` next to the `index.html`, the preview joins them automatically. Use **Larger** for a bigger view and **Reload** to start it again.

The preview runs in a sealed box: it has no internet, cannot read your Jarvis chats, and cannot send anything to Jarvis, so a page you do not trust cannot do harm from there. That also means a page that loads libraries or fonts from the internet (a CDN) will not work in the preview; Jarvis is told to write self-contained pages for this reason. To use such a page, download it and open it in your browser. Python and other languages are shown with colours but not run.

In the Routines settings, every step of a routine has its own **Edit** button (the step goes back into the form above; press **Update step**, or **Cancel**), arrows to move it up or down, and **×** to remove it. You no longer have to delete the steps after the one you want to change.

## Jarvis can see your screen

Ask Jarvis (typed, spoken, or from Telegram) things like “look at my screen”, “what's on my screen?”, “what's this error?”, “help me with this”, “what's wrong?” or, after it did something, “did that work?”. Jarvis takes a screenshot (hiding its own window first, so it sees what you see), gives it to a vision model together with your last few messages, and tells you what it sees, explains an error in plain words, says what to try, and says plainly when something did not work. From Telegram, `/look` does the same and the screenshot it looked at is sent back too.

**Check after phone commands (optional):** in **Settings > Daily > Telegram** tick “After that screenshot, let Jarvis look at it and tell me if the command did not work”. After each command from your phone (show the desktop, open an app, an approved action) Jarvis then adds a line starting with 🔍 saying whether the screen shows it worked, or what looks wrong (an error, a dialog waiting for you). It is off by default because a local vision model adds a wait.

This needs a vision model, the same one as for photos (see above). A small model such as moondream describes the screen but reads small text badly; if you have the memory for it, `ollama pull gemma3:4b` or `ollama pull qwen2.5vl:3b` reads error messages much better. With the local provider the screenshot never leaves your PC; with the cloud provider it is sent to that service, so do not ask it to look at anything private then. Screenshots you ask for from Telegram also pass through Telegram's servers.

Note: Jarvis only *looks* here. The separate **Computer** mode and Autopilot (which click and type for you) still need a capable cloud-style vision model that can point at things on the screen; a small local model is not good enough for that.

## Wake word: "Hey Jarvis"

Turn it on in **Settings > Voice > Wake word**. Jarvis then listens to the microphone, even when the window is closed and only the tray icon is running.

- Say **"Hey Jarvis, what's the weather"** in one go, or say **"Hey Jarvis"**, wait for the beep, and then ask.
- Answers are spoken with the Windows voice (you can turn that off). For about 6 seconds afterwards you can reply without saying the wake word again. Say **"stop listening"** to end the conversation.
- Actions that need approval are asked out loud: say **"yes"** to approve or **"no"** to dismiss.
- Everything is local. Speech is recognised on this PC with Whisper (the small `tiny` model for the wake word, `base` for what you ask; change with the environment variables `JARVIS_WAKE_MODEL` and `JARVIS_WHISPER_MODEL`). Nothing is recorded to disk and nothing goes to the internet.
- Needs the packages installed by `install-jarvis.bat` (sounddevice, numpy, faster-whisper). In Windows, allow desktop apps to use the microphone (Settings > Privacy & security > Microphone).
- If a TV or a conversation is nearby, Jarvis will use some CPU transcribing it (and ignores it unless it hears the wake word). Lower the sensitivity in Settings if that is a problem.

## Email: what arrived while you were away

Settings > **Mail** connects Jarvis to Gmail, read-only: it never sends, deletes, moves or marks anything as read.

1. In your Google account turn on 2-Step Verification, then open `myaccount.google.com/apppasswords`, name it "Jarvis" and copy the 16 letters. (In Gmail, Settings > Forwarding and POP/IMAP, IMAP must be on.)
2. Enter your Gmail address and the app password in Settings > Mail and press **Save and check now**.

Then ask "any new emails?" or "check my email" in the window, by voice ("Hey Jarvis...") or on Telegram (`/mail`). Jarvis says how many arrived since you last asked and what they were about. The morning briefing mentions new mail too (without marking it as told). You can limit it to Gmail's Primary tab so promotions and updates are skipped.

Privacy: the address and app password are stored only in `data/mail.json` in this folder (never in the zip). Summaries are written by your AI model. With a local model the emails never leave the PC. With a cloud model only senders and subjects are sent, unless you tick the box that also allows the first lines of each email. Some school or work networks block Gmail's mail port (993), as they can block Telegram. Disconnect removes the saved password; you can also revoke the app password in your Google account.

## Calendar and to-do list

Say or type it: "add buy milk to my to-do list", "add hand in the report by Friday to my to-do list", "schedule a dentist appointment on Friday at 3pm", "I have an exam on 20 November at 9", "what's on my calendar tomorrow / this week", "what's on my to-do list", "mark buy milk as done", "cancel the dentist appointment", "clear completed tasks". It works the same by voice and on Telegram (`/todo`, `/agenda`). Dates are day first (14/11 is 14 November); "at 5" means 5 pm and "at 9" means 9 am. Settings > **Planner** shows everything and lets you add, tick off and delete by hand. The morning briefing mentions today's events and tasks. Everything is stored in `data/planner.json`.

## Alerts on your phone

Settings > Planner > "Alerts to your phone" sends Telegram messages (once paired) when an event is coming up (default 15 minutes before), when a task comes due, when new email arrives (checked every 5 minutes, separate from "check my email"), and when the battery is at 20 percent or less and not charging. Events and tasks also pop up in the Jarvis window. "Send a test alert" checks that it works.

## Dictation anywhere

Settings > **Shortcuts**: hold a key (default Ctrl+Alt+D; Right Ctrl, F9 and F8 are also offered), speak, and let go. Jarvis types what you said where your cursor is, in any app. Hold for half a second before speaking, so normal shortcuts such as Ctrl+C never start it. Say "new line" or "new paragraph" to press Enter. Speech is recognised on this PC with Whisper (the same model as voice notes), so a first use can take a few seconds to load. It uses the microphone chosen for the wake word.

## Quick actions on selected text

Turn on in Settings > Shortcuts, then select text in any app and press Ctrl+Alt+Q (or Ctrl+Alt+E / F10). Jarvis opens a panel to Summarise, Fix writing, Explain, write a Reply, make it Shorter, Translate, or do something you type. **Copy** copies the result; **Replace selection** pastes it over the text you selected, so check it first. With nothing selected it uses the last thing you copied. The text goes to your chosen AI model, so with a cloud model it leaves the PC.

## Music controls

"Pause", "play", "resume the music", "next song", "previous song", "stop the music" and "what's playing" work from the window, by voice and on Telegram. They press the Windows media keys, so they control whichever player is active (Spotify, YouTube in a browser, VLC...). "What's playing" reads the Spotify window title or a YouTube tab; other players do not show it. Jarvis cannot search for and start a particular song.

## The Jarvis model

`jarvis` is a local Ollama model with Jarvis's settings and manner built in: a base model (qwen2.5:7b, about 4.7 GB, which fits an 8 GB graphics card) plus a temperature of 0.6, room for 8192 tokens and the J.A.R.V.I.S. persona. The recipe is `model\Modelfile`; the published template is `tools\jarvis.Modelfile`, and your own copy is made from it the first time and is never overwritten by updates.

Build it with `build-jarvis-model.bat`, with Settings > AI model > Jarvis model, or by saying "build the Jarvis model" at the PC. Ollama downloads the base model first if needed. When the build finishes, `jarvis` becomes the local model, and `start-jarvis.bat` picks it whenever it is installed (otherwise it starts on llama3.2:3b). To move to another base, or later to a fine-tuned GGUF file, change only the FROM line and rebuild. "Is the Jarvis model installed?" tells you where it stands, and the self-check includes it.

## Ollama starts by itself

If the Ollama model server is not running when Jarvis starts or when you send a message, Jarvis starts it (the Ollama tray app when it is installed, otherwise `ollama serve`).

## Settings is a popup you can search
Click the gear and Settings opens as a popup over the chat. The box at the top searches every setting at once: type "microphone", "app password" or "android" and only the matching settings stay on screen. Ctrl+K opens it with the search box ready, Esc or a click outside closes it. On a phone it fills the screen.

## Notes
Say or type "note that the exam is in room 204", "take a note: buy a USB cable" or "jot down the wifi is on the fridge". Later ask "what did I note about the exam?", "show my notes", "what's my last note?" or "delete the note about the cable". Notes are kept in `data/notes.json` on this PC, and Settings > Notes lists them with a search box. Notes are for things you want to look up later; "remember that my dog is called Rex" still goes to Memory, which Jarvis always keeps in mind.

## Follow-ups
Small local models often lose track of short messages like "the second one", "translate that" or "and in French?". Before such a message reaches the model, Jarvis adds a short note saying what it refers to (the item from the list it just gave, or its last answer). Nothing extra is sent to a model and it costs no time. "Do it again" repeats your previous request.

## Study mode
Say "quiz me on chapter 3" and Jarvis asks questions one at a time from your saved documents (Settings > Chats) and your notes, then marks your answers in your own words. "Skip" shows the answer, "stop quiz" ends it with a score. Other phrases: "quiz me with 10 questions", "flashcards on the heart" (say "show answer", then "got it" or "again"), "quiz me on what I got wrong" (asks the missed ones again) and "my study stats". When nothing in your documents or notes matches, the questions come from the model's own knowledge and Jarvis says so. "Plan revision for the chemistry exam on 20 November" adds the exam to your calendar and three revision tasks at 18:00 on the days before. Quality depends on the local model: a bigger one writes and marks better. Results are kept in `data/study.json`.

## Import a calendar (school timetable)
Settings > Planner > **Import a calendar**: paste an iCal link (ending in .ics, or starting with webcal://) or choose an .ics file. Google Calendar gives one under Settings > your calendar > "Secret address in iCal format"; many schools publish a timetable link. The next three weeks of lessons, with repeating lessons, changes and cancellations, appear in your calendar, the briefing and "what's on my calendar tomorrow". Jarvis only reads the calendar and never changes it. Links are read again every few hours ("Refresh now" does it straight away). Imported events do not send alerts, so your phone is not flooded with one message per lesson; tick the box in that section if you want them. A link is private: do not share it, and it is saved in `data/calendar.json`.

## Spotify
Settings > Shortcuts > **Spotify** connects Jarvis to your Spotify account so you can say "play Blinding Lights on Spotify", "play my workout playlist", "play the album Discovery by Daft Punk", "play some music by Queen" or "queue Yellow". Pause, skip and "what's playing" already work without it. Spotify only lets other programs choose songs for **Premium** accounts, and a Spotify player (the app on this PC or your phone) has to exist; Jarvis opens the PC app if none is running. One-time setup: create a free app at developer.spotify.com/dashboard, add the Redirect URI shown in Settings, paste the app's Client ID and press Connect. The login happens in your browser with Spotify's own page; Jarvis stores only a refresh token in `data/spotify.json` (never your login details, and no client secret is needed). Keep that file private. Spotify's own made-for-you playlists such as Discover Weekly are not available to new developer apps, so asking for them will search for a normal playlist instead.

## PC health
Ask "how's my PC?" or press **Settings > Daily > PC health > Check now**: free disk space, memory, how long the PC has been on, temp files, startup programs, the programs using the most memory, the last Windows update and the size of Jarvis's data and the Ollama models, with plain suggestions. "Clean up my temp files" says how much it would delete and waits for you to say "yes, clean them" (within two minutes). It only removes files in your temp folder older than 3 days, skips files in use, and never does it when asked from the phone (Telegram) or by voice.

## Backup and restore
Settings > Daily > **Backup** saves everything in your `data` folder (chats, settings, notes, tokens) into one encrypted `.jbk` file in the folder you choose (default `Documents/Jarvis-backups`, ideally a USB drive or cloud-synced folder). Pick a passphrase of at least 8 characters; it is never stored, so if you forget it the backup cannot be opened. To restore, pick a backup, type its passphrase and press Restore: your current data is first copied to `data-before-restore-<date>` next to it, so nothing is lost. Ask "when was my last backup?" in chat; the PC health report also reminds you after two weeks. Backups and restores only work at the PC, never from Telegram.

## Evening recap
Say "evening recap" (or "recap my day", "how was my day?") for a short look back and ahead: tasks you ticked off today, events that happened, notes you saved, what is still open or overdue, and tomorrow's events and due tasks. It uses only your planner and notes, so it works offline and sends nothing anywhere. Settings > Planner > **Evening recap** can also post it in the chat once a day at a time you choose (off by default; it is never spoken aloud and never pushed to Telegram, and switching it on after the chosen time waits until the next day).

## Smart commands (experimental)
Jarvis's built-in commands recognise set phrases. With **Settings > AI model > Smart commands** switched on, a message they do not recognise ("ugh, I've got a physics test on the 20th", "nudge me in 2 hours to call mum", "where did I write the wifi code?") is shown to the AI model together with a list of 22 tools: calendar, to-do list, notes, reminders, timers, quizzes, recap, briefing, weather, PC health, Spotify, web search, exams and revision, the focus timer, search across everything and the Wi-Fi check. The model answers with the tool to use, and Jarvis runs it with the same code as the built-in command. Under the reply you see which tool was chosen.

- **Safe by design:** only those tools exist for the model. Nothing that deletes, sends mail, touches files, backs up or updates is on the list. An answer Jarvis cannot trust (not valid, unknown tool, or details that are not in your message) is ignored and you get a normal chat answer instead.
- **Undo:** say "undo that" within ten minutes to take back the last task, event, note, reminder or timer it added.
- **Speed:** built-in commands still run first and instantly. Only messages that mention something tool-like cost one extra short question to the model.
- **Off by default.** How well it works depends on the model: small local models make more mistakes. What it decided is kept in `data/training/router.jsonl` (on this PC only, while the training log is on) so it can be measured.
- **Measure it before you switch it on:** start Jarvis, then double-click `evaluate-smart-commands.bat`. It runs 216 labelled example messages (148 that want a tool, 68 that must not trigger one) through your model without carrying anything out, and prints the scores: right tool (target 85% or more), false alarms (target 3% or less) and seconds per question. Mistakes are listed in `data/router-eval.json`. To include your own past messages, run `evaluate-smart-commands.bat --label` (you say which tool each logged message wanted; the labels stay in `data/`) and then `evaluate-smart-commands.bat --mine`.

## French commands
The built-in commands are also understood in French: "ajoute acheter du pain à ma liste", "qu'est-ce que j'ai demain ?", "rappelle-moi d'appeler maman demain à 18h", "mets un minuteur de 10 minutes", "note que le code est 4471", "interroge-moi sur la Révolution française", "récap de ma journée", "quel temps fait-il ?", "j'ai un contrôle de physique le 20", "planifie mes révisions", "concentration pendant 25 minutes", "quels appareils sont connectés au wifi", "cherche … sur internet". Jarvis rewrites the command words and the date words ("demain à 18h", "le 3 décembre", "dans 20 minutes") into the English command and leaves what you said (the task, the note) as you wrote it. The confirmation is then translated back into French by the AI model; if the model cannot be reached you get the English confirmation. Anything that is not one of the known commands goes to the chat model as before.

## Exams and revision
Any calendar event whose title says exam, test, quiz, contrôle, examen and so on counts as an exam, however it got into the calendar. "My chemistry exam is on 3 December at 9am" adds it and plans the revision in one go; "exam countdown" lists what is coming with the days left and how much revision is done (revision tasks ticked off, quizzes on the subject, focus minutes); "plan my revision" adds the missing "Revise …" tasks for every exam. Sessions fall 14, 10, 7, 5, 3, 2 and 1 days before the exam at 18:00, never more than two a day (a full evening moves the session to the nearest free day before the exam). Exams within a week appear in the briefing and the evening recap. Settings > Planner > **Exams and revision** shows the list and adds exams.

## Focus timer
"Focus for 25 minutes on maths" (or "pomodoro", "start a 50 minute focus session") starts a block of work followed by a break (5 minutes, or 10 after 50 minutes or more). While it runs Jarvis holds back its own proactive messages. "How long is left", "stop focus", "how much did I focus today / this week". Finished minutes are added up in the evening recap and count towards the exam they were for. Settings > Planner > **Focus timer** has Start and Stop buttons.

## Search across everything
"Search everything for the wifi code", "where did I write the locker number", "do I have anything about the science fair": one search over your notes, to-do list (including finished tasks), calendar (including past events), the things you asked Jarvis to remember, and your documents, with the results grouped by where they were found.

## Wi-Fi and network
- **"What devices are on my wifi"** lists the devices on your home network (address, name when the router gives one, "phone or tablet (private address)" for devices that hide their identity) and marks the ones that were not there before. "Name device 192.168.1.23 Mum's phone" labels one. The first time on a network Jarvis asks you to confirm it is your own ("yes, scan", at the PC only), because a scan lists everyone's devices: do not use it at school, at work or on public Wi-Fi.
- **"Why is my wifi slow"** measures the delay and loss to the router and to the internet, the Wi-Fi signal, band, link speed and how many neighbouring networks share the channel, and how much this PC itself is sending and receiving (with its busiest programs), then names the most likely cause.
- **"Watch my wifi"** (or the checkbox in Settings > Daily > Wi-Fi and network) checks every five minutes and tells you in the chat when the connection is clearly worse than usual twice in a row, or when a new device joins. Off by default.
- **What it cannot do:** a PC cannot see how much data another device uses; only the router knows that, and its own page often shows it. Devices that are asleep do not show up. The readings come from Windows tools (PowerShell, `netsh`, `ping`).

## Screen understanding and remote control
- **Screen map.** Besides the screenshot, Jarvis now reads what Windows itself reports about the front window: its title, every button, link, menu item, tab and text box with its name and position, and the text shown. The AI model gets that list with the picture, so "what's on my screen?" quotes names and wording exactly, and Autopilot can pick a control by its number instead of guessing pixel positions. With a model that cannot see pictures, "what's on my screen?" is answered from the list alone (and says so). Some apps and most games do not publish such a list; then only the picture is used.
- **"Click on Save"** (also "double click Documents", "right-click the Recycle Bin icon", "press the OK button", "clique sur Enregistrer") finds the control with that name in the front window and clicks it, without any AI model. If two controls match, Jarvis lists them and waits; greyed-out controls are not clicked.
- **Phone as mouse and keyboard.** In the Android app, PC tab > Live screen, switch on "Control the PC from here": a tap on the live picture clicks there, two taps double-click, holding right-clicks, dragging scrolls, and a text box types on the PC (accents included) with keys for Enter, arrows, copy/paste, Start, switch app and more. It only works after you tick **Settings > Daily > Phone app > Let the phone control the mouse and keyboard** on the PC, which cannot be changed from the phone. Frames and keystrokes travel over your Wi-Fi unencrypted, so do not type passwords this way.
- The app's Planner tab also shows, from the PC: the focus timer, exams and revision, notes and the evening recap; the PC tab has the Wi-Fi check; and messages Jarvis sends on its own (focus session done, evening recap, a new device on the Wi-Fi, updates) appear in the app and as a notification while the app is open.

## Find files by type
"Search for .pdf files in Documents", "find all .mp3 and .wav files on the D drive", "search for .py files in my School folder", "where are my .psd files", "search for .txt files on my computer", "cherche les fichiers .docx dans téléchargements". Jarvis lists the matching files, newest first, with their size and date, and the total size; "Show in folder" opens Explorer at the file.
- **Where:** a known folder (Desktop, Documents, Downloads, Pictures, Videos, Music, also inside OneDrive), any folder by its name under your user folder or one level inside those (if two folders share the name, both are searched), a full path, a drive ("the D drive"), or "my computer" for every drive. With no place named, your Desktop, Documents, Downloads, Pictures, Videos and Music folders are searched.
- **Types:** any extension with or without the dot, several at once, or a few words: word, excel, powerpoint, pdf, images, photos, videos, music, zip, python.
- Only names, sizes and dates are read; no file is opened. Windows, Program Files, AppData, the recycle bin, hidden folders and node_modules are skipped. A search stops after 20 seconds (45 for the whole computer) and says so.

## Which folder Jarvis runs from
The bottom of the chat list always shows the folder this copy of Jarvis is running from. Settings > Look > **This Jarvis** shows it in full with the data folder (chats, settings, notes), the Python it uses (and whether that is Jarvis's own `.venv`), the computer's name and when the program files last changed, with buttons to open either folder in Explorer or copy the path. In chat: "where are you running from?", "which folder is Jarvis in?", "open the Jarvis folder", "où es-tu installé ?". From Telegram it only tells you; it opens nothing.

## Changing documents
Add a document with the **+** button next to the message box (or drop it on the chat), then ask for a change in plain words:
- "fix the spelling mistakes in essay.docx", "make my cover letter more formal", "translate report.docx into French", "shorten the history report", "corrige les fautes dans essay.docx"
- "in budget.xlsx, replace 2025 with 2026", "replace "Mr Smith" with "Mrs Jones" in essay" (done at once, without the AI model)
- follow-ups work on the result: "now make it shorter"; "from the original, …" starts again from the file you gave.

You get a new file ("essay (edited).docx") with **Download** and **Show in folder** buttons; your original is never changed. Edits made by the AI model run in the background and the new file appears in the chat when ready.
- **Word, PowerPoint, Excel:** only the text that changes is rewritten; styles, tables, pictures, headers and footers are copied as they are. A paragraph the model rewrites takes the formatting of its first word (bold words in the middle of it become plain); a plain replacement keeps all formatting. In Excel, text cells can be changed by the model and both text and number cells by a replacement; formulas are never touched.
- **Text, Markdown, CSV and code files:** edited paragraph by paragraph, keeping the file's encoding and line endings.
- **PDF:** cannot be changed in place, so the result is a Word file with the edited text (the layout is not kept).
- The whole document goes to your chosen AI model in parts. With a cloud model it is sent to that provider; with Ollama it stays on this PC. Small local models make more mistakes, so read the result.
- Documents added before this version only have their text saved, not the file: add them again to change them. Edited files are kept in `data\documents\edited`.

## Self-check
"Run a self-check" (or Settings > Look > **Self-check**) tries each part of Jarvis that depends on this PC: Python packages, the data folder, the AI model (and how fast it answers), whether the model can see pictures, taking a screenshot, reading the controls and the text on the screen, the list of windows, mouse and keyboard, the network and Wi-Fi readings, file search, document editing, the phone link and the offline voice. It only reads and measures. The report is shown with ✓, ⚠ and ✗, can be copied with one button, and is saved in `data\selftest.txt`.

## Making new documents
Ask for a file and say what kind: "write a cover letter for a summer job at the bakery as a Word file", "make 8 slides on the water cycle", "a budget spreadsheet for my trip to Rome", "make a csv of the planets with their diameter", "write my revision notes on WW1 as a markdown file", "fais une présentation de 5 diapositives sur les volcans". The AI model writes the content and Jarvis builds a real Word, PowerPoint or Excel file (headings, bullet points, tables, bold and italic; slides with a title slide; spreadsheets with a bold header row, frozen headers and working formulas such as totals). It appears in the chat with **Download** and **Show in folder**, is kept in `data\documents\created`, and is added to your documents, so "make it shorter" or "translate it into French" works on it straight away. Missing details come as placeholders in [square brackets]. Jarvis cannot write PDFs directly: ask for a Word file and save it as PDF from Word.

## Smart commands that use earlier results
With Smart commands on, one request can now need several steps where a later step uses what an earlier one found: "when is my chemistry exam? remind me to revise two days before", "look up when the next solar eclipse in Spain is and save it as a note". The model first runs the steps it can, sees their results, then gives the next ones (at most three rounds and six steps). Values may come from your message or from those results; anything else is still refused, and a tool your message did not ask for is never used. "Undo that" takes back everything the chain changed. Reminders on a given day ("on 25 November at 6pm") now work too.

## Stronger computer control
- **Seeing more of the screen.** Each Autopilot step now gets the list of open windows, the controls Windows reports in the front window, and all the text on the screen read by Windows' own OCR (built into Windows 10 and 11, no download). The model can click a control or a line of text by its number, which is exact, instead of guessing a position in the picture. "What's on my screen?" uses the same text, so it can quote what is written anywhere on the screen.
- **Models that cannot see pictures** can now drive Autopilot from that text alone (Settings > AI model > Computer control > How Autopilot looks at the screen; Automatic picks text-only for models like llama3.2 that cannot see). It works well in ordinary apps and websites, less well in games or drawing apps that show no text.
- **Windows and apps.** Autopilot can bring a window to the front, maximise, minimise or restore it, open an app by name, open a web page or a folder.
- **Working on projects.** Add a project folder in Settings > AI model > Computer control. Inside it, Autopilot reads and writes files directly (it reads a file before changing it and writes the whole new version), instead of typing in an editor. Every file it overwrites is backed up in `data\file-backups\projects`; it never writes .exe, .bat, .ps1 or other files Windows runs directly, and it cannot reach anything outside those folders. It does not run commands or builds.
- **Longer runs.** Choose 20, 40 (default), 80 or 150 actions per run. Stop at any time with the Stop button or Ctrl+Shift+F10. The rules stay: no passwords, no sending, buying, deleting or installing unless you asked for exactly that.
- **Watching the screen.** "Watch my screen and tell me when the download finishes", "tell me when “Render complete” shows up on the screen", "surveille mon écran et dis-moi quand …". Jarvis reads the screen every five seconds; a quoted text or "X appears" is simply looked for, anything else is asked of the AI model at most every 20 seconds. It tells you (spoken and in the chat) when it happens, and stops after two hours or on "stop watching the screen".
- **Faster screen reading.** Reading the controls and the text on the screen used to start a new PowerShell each time, one to two seconds a look. Now a helper PowerShell stays running with UI Automation and the OCR engine already loaded, and asks Windows for all of a window's controls in one trip instead of one per property. The controls and the OCR text are read at the same time, from the step's own screenshot (taken once per step). The helper closes itself after three minutes unused. If it cannot start, Jarvis goes back to the old way by itself. The self-check shows how long one read takes.
- **Seeing what Autopilot is about to do.** Before each click Autopilot outlines the control on the screen ("Click: Save") for about half a second, and a bar shows the step and a **Stop** button; Stop during the outline means that action never happens. Clicks go through the outline, the bar moves out of the way of what Autopilot is about to click, and both are left out of screenshots so the AI model never sees them (on Windows older than 10 version 2004 they are hidden for each screenshot instead). Switch it off, or try it, in Settings > AI model > Computer control. It needs Python's tkinter, which the normal Python installer includes.
