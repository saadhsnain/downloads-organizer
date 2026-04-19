# Downloads Folder AI Organizer

Automatically sort files dropped into your Mac `~/Downloads` folder using Google Gemini. The script reads your existing subfolder structure and asks Gemini to decide where each new file belongs — no hardcoded rules, no category lists. It adapts to whatever folders you have.

**How it works:** A `launchd` agent runs `organizer.py` every day at 7pm. The script scans all loose files in `~/Downloads`, sends each filename, type, and a short content preview to Gemini, and moves each file into the best-matching subfolder.

---

## Quick Install

```bash
git clone https://github.com/YOUR_USERNAME/downloads-organizer.git
cd downloads-organizer
bash install.sh
```

The installer handles everything: API key, script placement, starter folders, and the background agent. **No manual steps required after running it.**

---

## Requirements

- macOS 12 or later
- Python 3 (pre-installed on macOS)
- A free Google Gemini API key

---

## Manual Setup (if you prefer not to use the installer)

### Step 1 — Get a Gemini API Key

1. Go to [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey) and sign in with your Google account.

> 📸 **[SCREENSHOT: Google AI Studio — API Keys page showing the "Create API key" button]**

2. Click **Create API key** and copy the key that appears. It looks like `AIzaSy...`.

> 📸 **[SCREENSHOT: The generated API key dialog with the copy button highlighted]**

---

### Step 2 — Set Up the Script

1. Copy `organizer.py` to `~/Scripts/`:

```bash
mkdir -p ~/Scripts
cp organizer.py ~/Scripts/organizer.py
chmod +x ~/Scripts/organizer.py
```

2. Create at least a few subfolders inside `~/Downloads`. The AI will use whatever folders exist — name them however you like:

```
~/Downloads/
  Images/
  Documents/
  Installers/
  Misc/
```

You can also use project or client names — the AI will figure it out from context.

> 📸 **[SCREENSHOT: Finder showing ~/Downloads with several subfolders like Images, Documents, Installers, Misc]**

---

### Step 3 — Add Your API Key

Add this to your `~/.zshrc` (or `~/.bash_profile`):

```bash
export ORGANIZER_API_KEY="paste-your-key-here"
```

Then reload: `source ~/.zshrc`

> ⚠️ Never paste the key directly into `organizer.py` if you plan to push to a public repo.

---

### Step 4 — Test It Manually

```bash
python3 ~/Scripts/organizer.py
```

This scans all loose files currently in `~/Downloads` root and sorts them. Check the log:

```bash
cat ~/Downloads/.organizer_log.txt
```

> 📸 **[SCREENSHOT: Terminal showing the organizer log output with a successful move entry]**

---

### Step 5 — Install the launchd Agent

The agent watches `~/Downloads` for changes and calls the script automatically.

1. Create `~/Library/LaunchAgents/com.user.downloads-organizer.plist` with this content (replace paths as needed):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.downloads-organizer</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/YOUR_USERNAME/Scripts/organizer.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ORGANIZER_API_KEY</key>
        <string>YOUR_API_KEY</string>
    </dict>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>19</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/Downloads/.organizer_log.txt</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/Downloads/.organizer_log.txt</string>
</dict>
</plist>
```

2. Load it:

```bash
launchctl load -w ~/Library/LaunchAgents/com.user.downloads-organizer.plist
```

> 📸 **[SCREENSHOT: Terminal showing the launchctl load command completing with no errors]**

---

## Verify It's Working

Drop any file into `~/Downloads`. Within a few seconds it should move into a subfolder.

Watch the log live:

```bash
tail -f ~/Downloads/.organizer_log.txt
```

A successful entry looks like:

```
[2026-04-19 13:45:02] Processing: invoice-march.pdf  |  folders: Documents, Images, Misc
[2026-04-19 13:45:03] ✓ 'invoice-march.pdf' → Documents/ (saved as 'invoice-march.pdf')
```

---

## Managing the Agent

```bash
# Stop the organizer
launchctl unload ~/Library/LaunchAgents/com.user.downloads-organizer.plist

# Start it again
launchctl load -w ~/Library/LaunchAgents/com.user.downloads-organizer.plist
```

---

## Customisation

| Setting | Where | Default |
|---|---|---|
| API key | `ORGANIZER_API_KEY` env var | (empty — must set) |
| Gemini model | `GEMINI_MODEL` in `organizer.py` | `gemini-2.5-flash-lite` |
| Fallback folder | `FALLBACK_FOLDER` in `organizer.py` | `Misc` |
| Local AI fallback | `OLLAMA_MODEL` in `organizer.py` | (disabled) |

**Changing your folder structure:** Just create or rename folders inside `~/Downloads`. The script re-scans on every run — no config needed.

**Ollama fallback:** If you run [Ollama](https://ollama.com) locally, set `OLLAMA_MODEL` to a model name (e.g. `llama3.2`) and the script will fall back to it when Gemini is unreachable.

---

## Troubleshooting

**Script never fires**
- Check the agent is loaded: `launchctl list | grep downloads-organizer`
- Reload it: `launchctl unload ~/Library/LaunchAgents/com.user.downloads-organizer.plist && launchctl load -w ~/Library/LaunchAgents/com.user.downloads-organizer.plist`

**Files go to Misc every time**
- Check `~/Downloads/.organizer_log.txt` for `API_KEY not set` or `Gemini API error`
- Confirm your key is valid at [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)

**File was not moved**
- The script only processes files sitting directly in `~/Downloads` root — files already in subfolders are ignored
- Check the log to confirm the file was seen, or run manually: `python3 ~/Scripts/organizer.py`
