#!/opt/homebrew/bin/python3
"""
Re-sort the files in one ~/Downloads subfolder into the other subfolders, using
the local Ollama classifier. Built for cleaning up files that landed in Misc/
during a Gemini outage, but works on any folder.

Goes straight to Ollama (not Gemini) — this is a bulk pass and Gemini may be
rate-limited; the local model is free. A file the model classifies back into the
source folder (or that it can't classify) stays put.

Usage:
  python3 redistribute.py            # dry run over Misc/ — prints the plan
  python3 redistribute.py --apply    # actually move
  python3 redistribute.py --folder Misc --apply
"""

import argparse
from pathlib import Path

import organizer as o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default="Misc", help="source subfolder (default: Misc)")
    ap.add_argument("--apply", action="store_true", help="actually move files (default: dry run)")
    args = ap.parse_args()

    source = o.DOWNLOADS / args.folder
    if not source.is_dir():
        raise SystemExit(f"no such folder: {source}")

    # Target folders = all Downloads subfolders (the source stays in the list so a
    # genuinely-unclassifiable file can remain where it is).
    folders = o.get_subfolders()

    files = sorted(p for p in source.iterdir()
                   if p.is_file() and not p.name.startswith("."))
    print(f"{'APPLY' if args.apply else 'DRY RUN'} — {len(files)} files in {args.folder}/\n")

    moved = stayed = failed = 0
    for f in files:
        info = o.get_file_info(f)
        target = o.classify_with_ollama(info, folders)
        if not target:
            print(f"  ?  {f.name}  (no classification — leaving)")
            failed += 1
            continue
        if target == args.folder:
            print(f"  ·  {f.name}  → stays in {args.folder}/")
            stayed += 1
            continue
        print(f"  →  {f.name}  → {target}/")
        moved += 1
        if args.apply:
            dest_folder = o.DOWNLOADS / target
            dest_folder.mkdir(exist_ok=True)
            dest = o.safe_move(f, dest_folder)
            o.log(f"✓ redistribute: '{f.name}' → {target}/ (saved as '{dest.name}')")

    print(f"\n{'moved' if args.apply else 'would move'}: {moved}   stays: {stayed}   unclassified: {failed}")


if __name__ == "__main__":
    main()
