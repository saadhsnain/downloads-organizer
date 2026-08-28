# Downloads Folder AI Organizer

Automatically sort files dropped into your Mac `~/Downloads` folder using Google Gemini. The script reads your existing subfolder structure and asks Gemini to decide where each new file belongs — no hardcoded rules, no category lists. It adapts to whatever folders you have.

**How it works:** A `launchd` agent runs `organizer.py` every day at 7pm. The script scans all loose files in `~/Downloads`, sends each filename, type, and a short content preview to Gemini, and moves each file into the best-matching subfolder.

---

## Quick Install

```bash
git clone https://github.com/saadhsnain/downloads-organizer.git
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


2. Click **Create API key** and copy the key that appears. It looks like `AIzaSy...`.


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


---

## One-Time Permission (Silence the macOS Dialog)

macOS protects `~/Downloads` under its privacy system and will show a permission dialog the first time Python tries to access it. To prevent this from appearing on every scheduled run, grant Python permanent access once:

1. Open **System Settings → Privacy & Security → Full Disk Access**
2. Find `python3` (or `python3.x`) in the list and toggle it **on**


If Python isn't in the list, click **+** and add it from `/opt/homebrew/bin/python3` (or wherever `which python3` points on your machine).

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

## 2026-08-28 — project-first routing

The classification prompt now applies a precedence rule: client/project folders win over
file-type folders, so a client's poster files under that client rather than `Images`. Personal
material (statements, contracts, IDs, credentials, chat exports) routes to `Personal` and
never to a client folder. Client hints let an abbreviation or a former role name
resolve to the same client.

Client staging folders and `Personal/` were added to `~/Downloads`.

Ollama fallback repointed from `qwen3.5:latest` to `glm-5.2:cloud` — the former was removed
from the machine. This is tier 3; Gemini and OpenRouter both remain configured.

## 2026-08-28 — canonical client names

Client staging folders now take their exact names from an external canonical
source (for this install, a Notion database), shared with the delivery folder in
Drive. The prompt tells the model to use the exact folder name rather than invent a
variant, and to treat a former name or renamed role as the same client.

## 2026-08-28 — lanes, and a sweep

The organizer was write-only for its whole life. It moved files into folders and
nothing ever took them out, so every folder was terminal and the only possible
direction was growth. Sorting by file type made that unfixable: a type folder has
no lifecycle, so it cannot have an expiry rule. `Images/` held a client's door
hanger, a wallpaper and a stale screenshot — same type, three different fates.

Folders are now **lanes**, chosen by what happens to the file next:

| Lane | Meaning | Expires |
|---|---|---|
| `_clients/<Name>` | work to be delivered; flushed to Drive `10 Clients/` | no |
| `_reference` | looked up again: icons, logos, brand assets, fonts | no |
| `_personal` | statements, contracts, IDs, credentials, chat exports | no |
| `_scratch/YYYY-MM` | everything else, and the answer whenever unsure | **yes** |

Client names are canonical, from the Notion Companies database — the same list
`cadastre drive` reconciles Google Drive against.

`_scratch` is dated on arrival and swept on a clock, so an unclassified file
expires by itself. The prompt now prefers `_scratch` over a low-confidence guess,
because a file parked there is cheap to recover and a file misfiled into the wrong
client folder is not.

    organizer.py --sweep            report what is past SWEEP_AFTER_DAYS (90)
    organizer.py --sweep --apply    remove it (macOS Trash where available)

The scheduled run **reports** the sweep and never applies it. An unattended job
that deletes personal files is a review-gate change under `~/AGENTS.md`; that
decision is not this script's to make.

## 2026-08-28 — client lane gets an exit

`_clients/` shipped write-only: files went in and nothing took them out, which is
the same fault the sweep was written to fix, reproduced in a new lane. The README
claimed client work "leaves for Drive" while nothing in the code touched Drive.
It does now.

    organizer.py --flush            report what is staged
    organizer.py --flush --apply    move it to Drive `10 Clients/<Name>/`

Staging is deliberate, not a fallback for an unmounted Drive. Classification is a
single API call, and when every tier fails it takes the fallback path silently —
writing straight through would sync that mistake into a client's folder before
anyone saw it. A pass through `_clients/` keeps a misroute local until the next run.

**A client folder is matched, never created.** If `10 Clients/<Name>` does not
exist the files are held back with a message, because creating it here would
invent a client behind `cadastre drive`'s back — that command owns reconciliation
against the Notion Companies database, and this one deliberately knows nothing
about Notion.

The scheduled run **applies the flush but only reports the sweep**. A flush moves
files between two folders you own and is undone by dragging them back; the sweep
removes them. Only the destructive half waits for a human.

### Fallback tiers

Ollama is disabled: `qwen3.5` was removed to reclaim disk, and `glm-5.2:cloud` is
hosted rather than local — it answers 402 without a subscription, so naming it
bought a tier that always failed. To restore, `ollama pull llama3.2:3b` and set
`OLLAMA_MODEL`. OpenRouter is currently returning 401 with a key present, so
**Gemini is effectively the only live tier**; when it is rate-limited, files take
the `_scratch` fallback and expire on the clock rather than piling up.

## 2026-08-28 — on-device classification

Tier 0 is now Apple's Foundation Models, running on this Mac via a small Swift
helper (`apple-classify.swift`, compiled to `.build/` on first use). Requires
macOS 26 with Apple Intelligence on; falls through to the cloud tiers on any
failure — no toolchain, no framework, build error, guardrail refusal.

Full chain: **Apple -> Gemini -> OpenRouter -> Ollama -> `_scratch/`**

Why it leads rather than backs up the chain:

- **Nothing leaves the Mac.** Classification sends a 500-character preview of the
  file, and that preview can be a bank statement, a signed contract, or a
  credentials file. The `_personal` lane exists because that material is
  sensitive; sending it to a third party to decide it is sensitive was backwards.
- **No rate limit.** The cloud tier's free quota was exhausted twice in one
  afternoon of testing, and every file that arrived meanwhile took the fallback
  path.
- ~0.24s per file against ~1s, no keys, no network.

### It needs its own prompt

The on-device model is roughly 3B parameters and cannot share the cloud prompt.
Measured on the same eight files:

| Prompt | Score |
|---|---|
| Cloud prompt, free text | 1/7 — routed a bank statement to a client folder |
| Cloud prompt + guided generation | 2/8 — collapsed to always naming the first option |
| Flat rule list + guided generation | **8/8 on-device only** |

Small models follow rules; they do not weigh a precedence argument. Guided
generation constrains the answer to the exact folder list, so it cannot reply
with prose or invent a folder. `CLIENT_HINTS` supplies the words that mean a
given client — a small model will not infer that an abbreviation or a renamed
role refers to a client the way a frontier model does. Hints live in
`local_config.json`, which is gitignored.

### Unsure escalates

The rule list ends "anything else, or unsure -> `_scratch`", so that answer is an
admission rather than a decision, and it escalates to the cloud tier. A confident
answer never escalates — which is what keeps personal material local: a bank
statement is classified on-device and never sent anywhere. In testing only three
of eight files reached the network, and neither `_personal` file was among them.
