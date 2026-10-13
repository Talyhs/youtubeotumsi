# Talyhs Studio — Windows desktop branch

This is an additive Windows desktop layer. It does not replace `app.py`, `youtube.py`, `render.yaml`, or the existing GitHub Actions workflow.

## What is included
- PySide6 Windows interface for topic, language (az/tr/en), duration, voice, format and local preview.
- Safe default: the GUI runs `youtube.py` in `PUBLISH_MODE=prepare`; it does not publish automatically.
- Optional Ollama local script generation, without a hosted text-generation API key.
- FFmpeg audio mastering profiles, optional background music at a controlled volume, and thumbnail text overlay.
- Optional WhisperX word-level subtitle alignment; when alignment fails or the language model is unavailable, the app falls back to the existing ASS subtitles and reports the reason.
- SQLite job history/checkpoints, topic calendar, asset-credit records, and read-only YouTube statistics.
- Separate dependency files so heavyweight WhisperX is not installed unless requested.

## Setup
1. Install Python 3.11 x64 and FFmpeg. Ensure `ffmpeg -version` and `ffprobe -version` work in Command Prompt.
2. Run `run_windows.bat`.
3. The existing pipeline needs Pexels or Pixabay credentials and, unless using the local-script override, Gemini credentials. Set secrets as environment variables or use a local untracked .env loader of your choice; never commit them.
4. To use local Ollama, install Ollama separately, start it, then pull a model such as `ollama pull qwen2.5:3b`. Select the local Ollama checkbox in the GUI.
5. For optional word-level alignment, activate the same virtual environment and run `pip install -r requirements-alignment.txt`. First-run model downloads require internet. Word-level alignment support varies by language; Azerbaijani alignment must be verified against real audio.
6. To build the Windows app, run `build_windows.bat` on Windows. It creates a desktop EXE and a separate `engine/TalyhsEngine.exe` bundle; keep the engine folder beside the desktop app. FFmpeg must still be installed and available in PATH. Place local `.env` and `token.json` beside the desktop EXE. PyInstaller is not a cross-compiler; build on the target OS.

## Secrets and OAuth
- Never commit `.env`, `token.json`, `client_secrets.json`, API keys, or generated media.
- Existing upload OAuth scope may only grant upload. The statistics tab requires a local OAuth token with YouTube read-only or broader compatible scope. Re-authorize locally if needed.
- This branch intentionally disables direct publishing from the first desktop iteration. Review the MP4 and thumbnail first; wire a separate explicit publish action after validating the OAuth flow and metadata.

## Recovery behavior
The SQLite database is stored under `studio_data/studio.db` and ignored by Git. Each run records the engine and mastering stages. If a run fails, the error is stored in history. The existing `youtube.py` is still a monolithic step, so a failure inside that engine currently requires rerunning the engine; later refactoring can checkpoint stock search, narration, and rendering individually.

## Tests
```powershell
py -3.11 -m pip install -r requirements.txt -r requirements-desktop.txt
pytest -q
```
