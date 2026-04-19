#!/bin/bash
set -e

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
RESET='\033[0m'

step()  { echo -e "\n${BLUE}${BOLD}▶ $1${RESET}"; }
ok()    { echo -e "  ${GREEN}✓${RESET} $1"; }
warn()  { echo -e "  ${YELLOW}⚠${RESET}  $1"; }
fatal() { echo -e "\n${RED}${BOLD}✗ $1${RESET}\n"; exit 1; }

# ─── Banner ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Downloads Folder AI Organizer — Installer${RESET}"
echo "────────────────────────────────────────────"

# ─── Sanity checks ───────────────────────────────────────────────────────────
step "Checking requirements"

[[ "$(uname)" == "Darwin" ]] || fatal "This installer is macOS-only."

if ! command -v python3 &>/dev/null; then
    fatal "python3 not found. Install it from https://www.python.org/downloads/"
fi
PYTHON=$(command -v python3)
ok "Python found: $PYTHON ($(python3 --version 2>&1))"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -f "$SCRIPT_DIR/organizer.py" ]] || fatal "organizer.py not found. Run this installer from inside the downloads-organizer directory."

# ─── API key ─────────────────────────────────────────────────────────────────
step "Gemini API Key"
echo ""
echo -e "  Get a free key at: ${BOLD}https://aistudio.google.com/apikey${RESET}"
echo ""

# Check if already set in environment
if [[ -n "$ORGANIZER_API_KEY" ]]; then
    ok "ORGANIZER_API_KEY is already set in your environment — skipping."
    API_KEY="$ORGANIZER_API_KEY"
else
    while true; do
        read -rp "  Paste your Gemini API key: " API_KEY
        API_KEY="$(echo "$API_KEY" | tr -d '[:space:]')"
        if [[ -z "$API_KEY" ]]; then
            warn "Key cannot be empty. Try again."
        elif [[ ${#API_KEY} -lt 20 ]]; then
            warn "That looks too short. Make sure you copied the full key."
        else
            break
        fi
    done

    # Write to shell rc file
    RC_FILE=""
    if [[ "$SHELL" == */zsh ]]; then
        RC_FILE="$HOME/.zshrc"
    elif [[ "$SHELL" == */bash ]]; then
        RC_FILE="$HOME/.bash_profile"
    fi

    if [[ -n "$RC_FILE" ]]; then
        # Remove any previous entry first
        if grep -q "ORGANIZER_API_KEY" "$RC_FILE" 2>/dev/null; then
            sed -i '' '/ORGANIZER_API_KEY/d' "$RC_FILE"
        fi
        echo "export ORGANIZER_API_KEY=\"$API_KEY\"" >> "$RC_FILE"
        ok "Key saved to $RC_FILE"
    else
        warn "Could not detect shell rc file. Add this line manually:"
        echo "    export ORGANIZER_API_KEY=\"$API_KEY\""
    fi
fi

# ─── Copy script ─────────────────────────────────────────────────────────────
step "Installing organizer.py"

SCRIPTS_DIR="$HOME/Scripts"
mkdir -p "$SCRIPTS_DIR"
DEST="$SCRIPTS_DIR/organizer.py"
cp "$SCRIPT_DIR/organizer.py" "$DEST"
chmod +x "$DEST"
ok "Copied to $DEST"

# ─── Create starter folders ───────────────────────────────────────────────────
step "Creating starter folders in ~/Downloads"

FOLDERS=("Documents" "Images" "Videos" "Audio" "Archives" "Installers" "Misc")
for folder in "${FOLDERS[@]}"; do
    TARGET="$HOME/Downloads/$folder"
    if [[ ! -d "$TARGET" ]]; then
        mkdir -p "$TARGET"
        ok "Created: $folder/"
    else
        ok "Already exists: $folder/ (skipped)"
    fi
done
echo ""
echo -e "  ${YELLOW}Tip:${RESET} Add any folder you like to ~/Downloads — the AI will use it automatically."

# ─── Install launchd agent ────────────────────────────────────────────────────
step "Installing launchd agent"

LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS"
PLIST="$LAUNCH_AGENTS/com.user.downloads-organizer.plist"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.downloads-organizer</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$DEST</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ORGANIZER_API_KEY</key>
        <string>$API_KEY</string>
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
    <string>$HOME/Downloads/.organizer_log.txt</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Downloads/.organizer_log.txt</string>
</dict>
</plist>
PLIST

ok "Written to $PLIST"

# Unload any previous version then load fresh
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST"
ok "Agent loaded and watching ~/Downloads"

# ─── Quick smoke test ────────────────────────────────────────────────────────
step "Smoke test"

ORGANIZER_API_KEY="$API_KEY" "$PYTHON" "$DEST" 2>/dev/null \
    && ok "Direct invocation works — check ~/Downloads/.organizer_log.txt for results" \
    || warn "Direct invocation failed — check $HOME/Downloads/.organizer_log.txt"

# ─── Done ────────────────────────────────────────────────────────────────────
echo ""
echo -e "────────────────────────────────────────────"
echo -e "${GREEN}${BOLD}  All done. No manual steps required.${RESET}"
echo -e "────────────────────────────────────────────"
echo ""
echo -e "  Drop any file into ${BOLD}~/Downloads${RESET} and it will be sorted automatically."
echo -e "  Logs: ${BLUE}~/Downloads/.organizer_log.txt${RESET}"
echo ""
echo -e "  To stop the organizer:  ${BLUE}launchctl unload $PLIST${RESET}"
echo -e "  To start it again:      ${BLUE}launchctl load -w $PLIST${RESET}"
echo ""
