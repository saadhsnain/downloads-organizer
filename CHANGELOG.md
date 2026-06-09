# downloads-organizer Changelog

## 2026-06-09 (OpenRouter middle fallback tier)

- Inserted **OpenRouter** between Gemini and Ollama: chain is now
  **Gemini → OpenRouter → Ollama → `Misc/`**. OpenRouter (cloud) is preferred over
  the local model because Ollama heats the Mac — local is now true last resort.
  Added `classify_with_openrouter()` + CONFIG (`OPENROUTER_API_KEY` from
  `~/.scripts.env`, `OPENROUTER_MODEL`, `OPENROUTER_URL`). Each tier
  disable-able via its `*_MODEL` constant.
- Model is `google/gemma-4-31b-it:free`. First tried
  `nvidia/nemotron-3.5-content-safety:free` (user's pick) but it's a *content-safety*
  classifier — it only judges safe/unsafe and returns `content:null`, never a folder
  number — so it was swapped for a general instruction-following model verified to
  return clean numbers (6/6 sample files correct, incl. `aws_keys.txt` → Passwords
  & Credentials from the content preview).
- `health.sh` now reports `OPENROUTER_API_KEY` as an optional secret.
- Note: the key must be added to `~/.scripts.env` with `export` (a bare
  `VAR=value` is not exported to the Python child process / launchd wrapper).

## 2026-06-09 (Ollama fallback + launchd log fix)

- **Enabled the local Ollama fallback** (`classify_with_ollama` was already coded
  but disabled). `OLLAMA_MODEL = "qwen3.5:latest"`. Classification chain is now
  **Gemini → Ollama → `Misc/`**, so when Gemini is offline or rate-limited (429)
  the local model classifies instead of dumping everything into `Misc/`.
- Added `think: false`, `temperature: 0`, and `num_predict: 50` to the Ollama
  request — qwen3.5 returns an *empty* response if it spends the token budget on
  reasoning, so thinking must be disabled. Verified: correct folders on a 5-file
  test (~2–4s/file warm, ~19s cold load), and the full chain falls through to
  Ollama when the Gemini key is absent.
- Added `redistribute.py` — re-sorts one Downloads subfolder into the others via
  the local Ollama classifier (dry-run by default, `--apply` to move; idempotent).
  Used it to clean up the 130 files that had been dumped in `Misc/` during the
  Gemini outage: 125 redistributed into proper folders, 5 correctly kept
  (4 `.crdownload` in-progress downloads + 1 extensionless key file).
- Moved the launchd `StandardOut/ErrPath` out of `~/Downloads` (TCC-protected →
  silent exit 78, job hadn't run since 2026-03-26) to
  `organizer_launchd.log` in the script dir.
