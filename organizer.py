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
import json
import shutil
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

# Optional: local Ollama fallback when Gemini is unreachable.
# Set OLLAMA_MODEL = "" to disable the fallback entirely.
OLLAMA_MODEL = ""
OLLAMA_URL = "http://localhost:11434/api/generate"

# Folder name used when the AI can't confidently classify a file.
# Auto-created inside ~/Downloads if it doesn't already exist.
FALLBACK_FOLDER = "Misc"

# ─── END CONFIG ──────────────────────────────────────────────────────────────

DOWNLOADS = Path.home() / "Downloads"
LOG_FILE = DOWNLOADS / ".organizer_log.txt"

READABLE_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".html",
    ".py", ".js", ".ts", ".sh", ".yaml", ".yml"
}

IGNORED_FOLDERS = {".DS_Store", ".localized"}


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}\n"
    with open(LOG_FILE, "a") as f:
        f.write(entry)
    print(entry, end="")


def get_subfolders() -> list[str]:
    """Scan ~/Downloads and return all existing subfolder names."""
    folders = []
    for item in DOWNLOADS.iterdir():
        if item.is_dir() and item.name not in IGNORED_FOLDERS and not item.name.startswith("."):
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


def classify_with_ollama(file_info: dict, folders: list[str]) -> str | None:
    if not OLLAMA_MODEL:
        return None
    prompt, numbered = build_prompt(file_info, folders)
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 1024},
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
    result = classify_with_gemini(file_info, folders)
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
    folder_name = classify_file(file_info, folders)
    dest_folder = DOWNLOADS / folder_name
    dest_folder.mkdir(exist_ok=True)
    dest = safe_move(file_path, dest_folder)
    log(f"✓ '{file_path.name}' → {folder_name}/ (saved as '{dest.name}')")


def main():
    """
    Called by Folder Action with new file paths as arguments.
    Run with no arguments to organize everything currently in ~/Downloads root.
    """
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            file_path = Path(arg)
            if file_path.exists():
                organize_file(file_path)
    else:
        log("Manual run — organizing all loose files in ~/Downloads...")
        for item in sorted(DOWNLOADS.iterdir()):
            organize_file(item)
        log("Done.")


if __name__ == "__main__":
    main()
