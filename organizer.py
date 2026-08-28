#!/usr/bin/env python3
from __future__ import annotations
"""
Downloads Folder AI Organizer
Dynamically scans ~/Downloads for existing subfolders and uses Gemini
to decide where each new file belongs — including client-named folders.

Setup:
  1. Set your Gemini API key: export ORGANIZER_API_KEY="your-key-here"
     Or paste it directly into the API_KEY line in CONFIG below.
  2. Create subfolders in ~/Downloads however you like (by type, by client, etc.)
  3. Attach to Downloads via macOS Folder Action (see README.md)
"""

import os
import sys
import time
import json
import shutil
import subprocess
import mimetypes
import urllib.request
from pathlib import Path
from datetime import datetime

# ─── CONFIG ──────────────────────────────────────────────────────────────────

# Option A: set env variable ORGANIZER_API_KEY before running (recommended)
# Option B: paste your key as the second argument to .get() below
# Get a free key at: https://aistudio.google.com/apikey
API_KEY = os.environ.get("ORGANIZER_API_KEY", "")

# Gemini model to use.
# gemini-2.5-flash-lite  — fastest, cheapest, no thinking; ideal for classification
# gemini-2.0-flash       — slightly smarter, still very fast
GEMINI_MODEL = "gemini-2.5-flash-lite"

# Fallback tier 1 (cloud): OpenRouter, used when Gemini is unreachable/rate-limited.
# Preferred over the local model because it doesn't tax the Mac. Set
# OPENROUTER_API_KEY in ~/.scripts.env. Set OPENROUTER_MODEL = "" to skip this tier.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
# Must be a general instruction-following model. (The nemotron *content-safety*
# model only judges safe/unsafe and never returns a folder number — don't use it.)
OPENROUTER_MODEL = "google/gemma-4-31b-it:free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Tier 0 (preferred): Apple's on-device Foundation Models, via a small Swift
# helper compiled on first use. Free, ~0.24s, no keys, no rate limit — and
# nothing leaves the Mac, which matters because classification sends a preview
# of the file, and that preview can be a bank statement or a signed contract.
# Set APPLE_MODEL = False to skip this tier.
APPLE_MODEL = True

# Site-specific settings — your Drive path and your clients — live in
# local_config.json, which is gitignored. See local_config.example.json.
# Nothing about who you work with belongs in a public repository.
LOCAL_CONFIG = Path(__file__).resolve().parent / "local_config.json"
_local = {}
if LOCAL_CONFIG.exists():
    try:
        _local = json.loads(LOCAL_CONFIG.read_text())
    except (ValueError, OSError):
        _local = {}

# Extra words that mean a given client, for the on-device tier's rule list. A
# small model matches literally: it will not infer that an abbreviation or a
# renamed role refers to a given client the way a frontier model does. Keys are
# folder names under _clients/.
CLIENT_HINTS = _local.get("client_hints", {})

# Fallback tier 2 (local, last resort): Ollama. Runs the model on this Mac, which
# heats it up — only used if both Gemini and OpenRouter fail.
#
# Disabled. There is no local model installed to point it at: qwen3.5 was removed
# to reclaim 6.6 GB, and the only entry left, `glm-5.2:cloud`, is hosted rather
# than local — it answers 402 Payment Required without an Ollama subscription, so
# naming it here bought a tier that always fails. An honestly empty tier is better
# than one that pretends. To restore, pull a small local model (`ollama pull
# llama3.2:3b`, ~2 GB) and put its tag here.
# Full chain: Gemini -> OpenRouter -> Ollama -> _scratch/.
OLLAMA_MODEL = ""
OLLAMA_URL = "http://localhost:11434/api/generate"

# Where a file goes when the AI can't confidently classify it. This is a lane,
# not a graveyard: `_scratch/YYYY-MM/` is dated on arrival and swept on a clock,
# so an unclassified file expires by itself instead of accumulating forever.
FALLBACK_FOLDER = "_scratch"

# Lanes that never expire, because each answers "and then what?" on its own:
# client folders leave for Drive, _reference is looked up again, _personal is
# kept deliberately. Only _scratch has a clock.
CLIENTS_LANE = "_clients"

# Where client work is delivered. `_clients/<Name>/` is a staging area, not a
# destination: the flush moves it here, and this is the folder `cadastre drive`
# reconciles against the Notion Companies database.
CLIENTS_DRIVE = Path(
    _local.get("clients_drive", "")
).expanduser() if _local.get("clients_drive") else None
SWEEP_LANE = "_scratch"
SWEEP_AFTER_DAYS = 90

# ─── END CONFIG ──────────────────────────────────────────────────────────────

DOWNLOADS = Path.home() / "Downloads"
LOG_FILE = DOWNLOADS / ".organizer_log.txt"
TRASH = Path.home() / ".Trash"

READABLE_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".html",
    ".py", ".js", ".ts", ".sh", ".yaml", ".yml"
}

IGNORED_FOLDERS = {".DS_Store", ".localized"}

# Suffixes browsers and download managers use for a file still being written.
# Moving one either breaks the download or races it to disappearing mid-copy —
# both were happening, and the partial files left behind looked like ordinary junk.
IN_PROGRESS_SUFFIXES = {".crdownload", ".download", ".part", ".partial", ".tmp", ".opdownload"}


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}\n"
    with open(LOG_FILE, "a") as f:
        f.write(entry)
    print(entry, end="")


def get_subfolders() -> list[str]:
    """Scan ~/Downloads and return the lanes a file can be routed into.

    Top-level lanes, plus one level inside `_clients/` so each client is its own
    target. Discovery used to be top-level only, which forced every client to
    live at the Downloads root and put the root back on the path to sprawl —
    the exact failure the lanes were introduced to end. Nesting keeps the root
    at four fixed entries however many clients accumulate, and mirrors Drive's
    `10 Clients/<Client>` so one vocabulary describes both.
    """
    folders = []
    for item in DOWNLOADS.iterdir():
        if not item.is_dir() or item.name in IGNORED_FOLDERS or item.name.startswith("."):
            continue
        if item.name == CLIENTS_LANE:
            folders += [f"{CLIENTS_LANE}/{c.name}" for c in item.iterdir()
                        if c.is_dir() and not c.name.startswith(".")]
        else:
            folders.append(item.name)
    if FALLBACK_FOLDER not in folders:
        folders.append(FALLBACK_FOLDER)
    return sorted(folders)


def read_file_preview(file_path: Path, max_chars: int = 500) -> str:
    if file_path.suffix.lower() in READABLE_EXTENSIONS:
        try:
            return file_path.read_text(errors="ignore")[:max_chars]
        except Exception:
            pass
    return ""


def get_file_info(file_path: Path) -> dict:
    mime_type, _ = mimetypes.guess_type(str(file_path))
    stat = file_path.stat()
    preview = read_file_preview(file_path)
    return {
        "filename": file_path.name,
        "extension": file_path.suffix.lower(),
        "mime_type": mime_type or "unknown",
        "size_kb": round(stat.st_size / 1024, 1),
        "preview": preview,
    }


def build_prompt(file_info: dict, folders: list[str]) -> tuple[str, dict]:
    numbered = {str(i + 1): name for i, name in enumerate(folders)}
    folder_list = "\n".join(f"{i}. {name}" for i, name in numbered.items())
    prompt = f"""You are a file organizer for a Mac Downloads folder.

Given the file details below, pick the single most appropriate folder from the numbered list.
The folders may include file-type categories (e.g. Images, Documents) AND client or project names.
Use the filename, extension, and any content preview to make the best decision.

The folders are LANES, not file types. Each lane answers "and then what happens to
this file?", so pick on destiny, not on extension:

1. A `_clients/<Name>` folder — work that will end up delivered to that client.
   Choose it whatever the file type is: a poster for a client is that client's
   material, not an image; their deck is theirs, not a presentation.
2. `_reference` — something looked up again later: icons, logos, brand assets,
   wallpapers, fonts, cheat sheets. Not a document you read once.
3. `_personal` — financial statements, signed contracts, ID and visa documents,
   passwords, backup codes, exported chat logs. Never a client folder.
4. `_scratch` — everything else, and the right answer whenever you are unsure.
   It is dated and swept automatically, so putting a file here is cheap and
   reversible; guessing a client folder wrong is not. Prefer `_scratch` over a
   low-confidence guess.

Client folder names are canonical and come from the Notion Companies database. Use the
exact folder name in the list; do not invent a variant.

Client folder names are exact. An organisation may be referred to by an
abbreviation, a former name, or a role title that has since been renamed; treat
those as the same client.

File details:
- Name: {file_info['filename']}
- Extension: {file_info['extension']}
- MIME type: {file_info['mime_type']}
- Size: {file_info['size_kb']} KB
- Content preview: {file_info['preview'] or '(binary file, no preview)'}

Available folders:
{folder_list}

Reply with ONLY the number of the best matching folder.
Single number only. No words, no punctuation, no explanation."""
    return prompt, numbered


def strip_thinking(text: str) -> str:
    import re
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def parse_number(result_text: str, numbered: dict) -> str | None:
    cleaned = strip_thinking(result_text)
    number = cleaned.strip().split()[0].rstrip(".") if cleaned.strip() else ""
    return numbered.get(number)


APPLE_SRC = Path(__file__).resolve().parent / "apple-classify.swift"
APPLE_BIN = Path(__file__).resolve().parent / ".build" / "apple-classify"


def build_apple_prompt(file_info: dict, folders: list[str]) -> str:
    """A short, rule-shaped prompt, written for a ~3B model.

    It cannot share the cloud prompt. Given that one, the on-device model scored
    1/7 as free text and 2/8 under guided generation — where it collapsed to
    always naming the first option. Rewritten as a flat rule list it scores 6/8.
    Small models follow rules; they do not weigh a precedence argument.
    """
    lines = []
    for f in folders:
        if f.startswith(f"{CLIENTS_LANE}/"):
            client = f.split("/", 1)[1]
            words = ", ".join(CLIENT_HINTS.get(client, [client]))
            lines.append(f"- mentions {words} -> {f}")
    lines += [
        "- bank, statement, contract, passport, visa, password, backup code -> _personal",
        "- logo, icon, font, brand asset, wallpaper -> _reference",
        "- anything else, or unsure -> _scratch",
    ]
    rules = "\n".join(lines)
    return (
        "Classify a downloaded file into one folder.\n\n"
        f"Rules:\n{rules}\n\n"
        f"Filename: {file_info['filename']}\n"
        f"Content: {file_info['preview'] or '(none)'}\n\n"
        "Which folder?"
    )


def ensure_apple_binary() -> Path | None:
    """Compile the Swift helper on first use, or when the source changes.

    Returns None on any failure — a missing toolchain, a compile error, an older
    macOS without the framework. Every one of those is a reason to fall through
    to the cloud tiers, not to fail the run.
    """
    if not APPLE_SRC.exists():
        return None
    if APPLE_BIN.exists() and APPLE_BIN.stat().st_mtime >= APPLE_SRC.stat().st_mtime:
        return APPLE_BIN
    APPLE_BIN.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["swiftc", "-O", str(APPLE_SRC), "-o", str(APPLE_BIN)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log(f"Apple: build failed, skipping tier ({r.stderr.strip().splitlines()[-1][:120]})")
        return None
    return APPLE_BIN


def classify_with_apple(file_info: dict, folders: list[str]) -> str | None:
    if not APPLE_MODEL:
        return None
    binary = ensure_apple_binary()
    if binary is None:
        return None
    try:
        r = subprocess.run([str(binary)] + folders,
                           input=build_apple_prompt(file_info, folders),
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"Apple: {exc}")
        return None
    if r.returncode != 0:
        # A guardrail refusal ("May contain sensitive content") lands here. It
        # fires on precisely the material _personal exists for, so it is
        # expected rather than exceptional; the cloud tier picks it up.
        reason = "refused (sensitive content)" if "sensitive" in r.stderr else r.stderr.strip()[:100]
        log(f"Apple: {reason}")
        return None
    choice = r.stdout.strip()
    if choice not in folders:
        return None
    if choice == FALLBACK_FOLDER:
        # The rule list this tier is given ends "anything else, or unsure ->
        # _scratch", so the fallback lane is not an answer, it is an admission.
        # Escalate it and let the cloud tier try. A confident answer never
        # escalates, which is what keeps _personal material on this machine:
        # a bank statement is classified locally and never sent anywhere.
        return None
    return choice


def classify_with_gemini(file_info: dict, folders: list[str]) -> str | None:
    if not API_KEY:
        log("Gemini: API_KEY not set. Set ORGANIZER_API_KEY env variable or edit CONFIG in organizer.py.")
        return None
    prompt, numbered = build_prompt(file_info, folders)
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 20},
    }).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={API_KEY}"
    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        candidates = data.get("candidates", [])
        if not candidates:
            block = data.get("promptFeedback", {}).get("blockReason", "unknown")
            log(f"Gemini: no candidates (blockReason: {block})")
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        result_text = next((p.get("text", "").strip() for p in parts if p.get("text", "").strip()), "")
        if not result_text:
            finish = candidates[0].get("finishReason", "unknown")
            log(f"Gemini: empty response (finishReason: {finish})")
            return None
        folder = parse_number(result_text, numbered)
        if folder:
            return folder
        log(f"Gemini unexpected value: '{result_text}'")
        return None
    except Exception as e:
        log(f"Gemini API error: {e}")
        return None


def classify_with_openrouter(file_info: dict, folders: list[str]) -> str | None:
    if not (OPENROUTER_API_KEY and OPENROUTER_MODEL):
        return None
    prompt, numbered = build_prompt(file_info, folders)
    payload = json.dumps({
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 20,
        "temperature": 0,
    }).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    }
    try:
        req = urllib.request.Request(OPENROUTER_URL, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        choices = data.get("choices", [])
        if not choices:
            log(f"OpenRouter: no choices ({json.dumps(data)[:200]})")
            return None
        result_text = (choices[0].get("message", {}).get("content") or "").strip()
        if not result_text:
            log("OpenRouter: empty response")
            return None
        folder = parse_number(result_text, numbered)
        if folder:
            return folder
        log(f"OpenRouter unexpected value: '{result_text}'")
        return None
    except Exception as e:
        log(f"OpenRouter API error: {e}")
        return None


def classify_with_ollama(file_info: dict, folders: list[str]) -> str | None:
    if not OLLAMA_MODEL:
        return None
    prompt, numbered = build_prompt(file_info, folders)
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,  # qwen3.5 returns an empty response if it spends the budget thinking
        "options": {"num_predict": 50, "temperature": 0},
    }).encode()
    try:
        req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        result_text = data.get("response", "").strip()
        if not result_text:
            log("Ollama: empty response")
            return None
        folder = parse_number(result_text, numbered)
        if folder:
            return folder
        log(f"Ollama unexpected value: '{result_text}'")
        return None
    except Exception as e:
        log(f"Ollama error: {e}")
        return None


def classify_file(file_info: dict, folders: list[str]) -> str:
    result = classify_with_apple(file_info, folders)
    if result:
        return result
    result = classify_with_gemini(file_info, folders)
    if result:
        return result
    if OPENROUTER_API_KEY and OPENROUTER_MODEL:
        log(f"Falling back to OpenRouter ({OPENROUTER_MODEL})...")
        result = classify_with_openrouter(file_info, folders)
        if result:
            return result
    if OLLAMA_MODEL:
        log(f"Falling back to Ollama ({OLLAMA_MODEL})...")
        result = classify_with_ollama(file_info, folders)
        if result:
            return result
    return FALLBACK_FOLDER


def safe_move(src: Path, dest_folder: Path) -> Path:
    dest = dest_folder / src.name
    if dest.exists():
        stem, suffix = src.stem, src.suffix
        counter = 1
        while dest.exists():
            dest = dest_folder / f"{stem} ({counter}){suffix}"
            counter += 1
    shutil.move(str(src), str(dest))
    return dest


def should_skip(file_path: Path) -> bool:
    if file_path.is_dir():
        return True
    if file_path.name.startswith("."):
        return True
    if file_path == LOG_FILE:
        return True
    if file_path.name == "organizer.py":
        return True
    if file_path.parent != DOWNLOADS:
        return True
    if file_path.suffix.lower() in IN_PROGRESS_SUFFIXES:
        return True
    return False


def organize_file(file_path: Path):
    if should_skip(file_path):
        return
    folders = get_subfolders()
    if not folders:
        log(f"No subfolders found in {DOWNLOADS} — create at least one folder first.")
        return
    log(f"Processing: {file_path.name}  |  folders: {', '.join(folders)}")
    file_info = get_file_info(file_path)
    if not file_path.exists():
        return                      # finished, renamed, or cancelled since listing
    folder_name = classify_file(file_info, folders)
    dest_folder = DOWNLOADS / folder_name
    if folder_name == SWEEP_LANE:
        # Date the bucket on arrival so the sweep clock starts now.
        dest_folder = dest_folder / datetime.now().strftime("%Y-%m")
    dest_folder.mkdir(parents=True, exist_ok=True)
    try:
        dest = safe_move(file_path, dest_folder)
    except (FileNotFoundError, OSError) as exc:
        log(f"✗ '{file_path.name}' skipped: {exc}")
        return
    log(f"✓ '{file_path.name}' → {folder_name}/ (saved as '{dest.name}')")


def flush(apply: bool) -> int:
    """Move staged client work out to Google Drive.

    `_clients/` was write-only when it was introduced — the same fault the sweep
    was written to fix, reproduced in a new lane. This is its exit.

    Staging is deliberate rather than a fallback for an unmounted Drive. The
    classifier is a single API call, and when every tier fails it takes the
    fallback path silently; writing straight through would sync that mistake
    into a client's folder before anyone saw it. A pass through `_clients/`
    means a misroute stays local until the next run.

    A client folder is only ever *matched*, never created. If `10 Clients/<Name>`
    does not exist, the client is unregistered and the files stay put — creating
    it here would invent a client behind `cadastre drive`'s back, which owns that
    reconciliation against Notion.
    """
    lane = DOWNLOADS / CLIENTS_LANE
    if not lane.is_dir():
        return 0
    if CLIENTS_DRIVE is None:
        log("Flush: no clients_drive configured (see local_config.example.json).")
        return 0
    if not CLIENTS_DRIVE.is_dir():
        log("Flush: delivery folder not mounted — client work stays staged.")
        return 0

    moved = unknown = 0
    for client in sorted(lane.iterdir()):
        if not client.is_dir() or client.name.startswith("."):
            continue
        files = [f for f in client.rglob("*")
                 if f.is_file() and f.name not in {".DS_Store", ".keep"}]
        if not files:
            continue
        dest_root = CLIENTS_DRIVE / client.name
        if not dest_root.is_dir():
            log(f"Flush: no Drive folder for '{client.name}' — "
                f"{len(files)} file(s) held back. Register it, then re-run.")
            unknown += len(files)
            continue
        for f in files:
            dest_dir = dest_root / f.relative_to(client).parent
            if apply:
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = safe_move(f, dest_dir)
                # Log the path actually written, not just the basename — a file
                # landing in a subfolder should say so.
                log(f"  -> 10 Clients/{dest.relative_to(CLIENTS_DRIVE)}")
            moved += 1
    if apply:
        prune_empty(lane)

    if moved:
        log(f"Flush: {moved} file(s) {'delivered to' if apply else 'ready for'} Drive."
            + ("" if apply else " Re-run with --apply."))
    elif not unknown:
        log("Flush: nothing staged.")
    return moved


def prune_empty(lane: Path) -> None:
    """Remove dated buckets that no longer hold anything.

    A directory holding nothing but .DS_Store is empty in every sense that
    matters; counting it as occupied is what leaves 2018-04/ behind long after
    its contents expired. Runs whether or not anything was swept this time,
    because a bucket can also be emptied by hand.
    """
    for d in sorted(lane.rglob("*"), key=lambda p: -len(p.parts)):
        if not d.is_dir() or d == lane:
            continue
        if [x for x in d.iterdir() if x.name != ".DS_Store"]:
            continue
        for x in d.iterdir():
            x.unlink()
        d.rmdir()


def sweep(days: int, apply: bool) -> int:
    """Expire files that have sat in the sweep lane past their welcome.

    The organizer was write-only for its whole life: it moved files in and
    nothing ever took them out, so every folder was terminal and the only
    possible direction was growth. This is the other half. It touches nothing
    outside `_scratch/` — client folders leave for Drive on their own schedule,
    and `_reference/` is meant to persist.

    Dry run by default. Deletions go to the macOS Trash when `send2trash` is
    available, and are reported as hard deletes when it is not, so the operator
    always knows which one they are getting.
    """
    lane = DOWNLOADS / SWEEP_LANE
    if not lane.is_dir():
        log(f"No {SWEEP_LANE}/ to sweep.")
        return 0
    cutoff = time.time() - days * 86400
    stale = [f for f in lane.rglob("*")
             if f.is_file() and f.name not in {".DS_Store", ".keep"}
             and f.stat().st_mtime < cutoff]
    if not stale:
        log(f"Sweep: nothing in {SWEEP_LANE}/ older than {days} days.")
        if apply:
            prune_empty(lane)
        return 0

    total = sum(f.stat().st_size for f in stale)
    by_bucket: dict[str, int] = {}
    for f in stale:
        bucket = f.relative_to(lane).parts[0]
        by_bucket[bucket] = by_bucket.get(bucket, 0) + 1
    log(f"Sweep: {len(stale)} file(s), {total / 1e6:.0f} MB, older than {days} days")
    for bucket in sorted(by_bucket):
        log(f"    {bucket}  {by_bucket[bucket]} file(s)")

    if not apply:
        log("Dry run — nothing removed. Re-run with --apply.")
        return 0

    def to_trash(path: str) -> None:
        """macOS has a Trash; use it rather than unlink. Recoverable beats tidy,
        and the sweep runs on a clock — a wrong expiry rule should cost a drag
        back out of the Trash, not the file."""
        src = Path(path)
        dest = TRASH / src.name
        n = 1
        while dest.exists():
            dest = TRASH / f"{src.stem} ({n}){src.suffix}"
            n += 1
        shutil.move(str(src), str(dest))

    try:
        from send2trash import send2trash
        drop, how = send2trash, "moved to Trash"
    except ImportError:
        drop, how = (to_trash, "moved to Trash") if TRASH.is_dir() \
            else (lambda p: Path(p).unlink(), "deleted")
    for f in stale:
        try:
            drop(str(f))
        except Exception as exc:
            log(f"    failed on {f.name}: {exc}")
    prune_empty(lane)
    log(f"Sweep: {len(stale)} file(s) {how}.")
    return len(stale)


def main():
    """
    Called by Folder Action with new file paths as arguments.
    Run with no arguments to organize everything currently in ~/Downloads root.
    Run with --sweep to expire stale files instead of filing new ones.
    """
    if "--sweep" in sys.argv:
        sweep(SWEEP_AFTER_DAYS, apply="--apply" in sys.argv)
        return
    if "--flush" in sys.argv:
        flush(apply="--apply" in sys.argv)
        return

    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            file_path = Path(arg)
            if file_path.exists():
                organize_file(file_path)
    else:
        log("Manual run — organizing all loose files in ~/Downloads...")
        for item in sorted(DOWNLOADS.iterdir()):
            organize_file(item)
        # Delivering staged client work runs for real; expiring files does not.
        # The difference is that a flush *moves* files between two folders the
        # operator owns and is undone by dragging them back, while the sweep
        # removes them. Only the destructive half waits for a human.
        flush(apply=True)
        sweep(SWEEP_AFTER_DAYS, apply=False)
        log("Done.")


if __name__ == "__main__":
    main()
