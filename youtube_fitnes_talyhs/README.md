# English Fitness Shorts Automation

This module creates 30–60 second **English-only** vertical fitness videos for your separate fitness YouTube channel. Titles, narration, on-screen captions, descriptions, hashtags, and stock-footage search terms must all be in English.

## Features
- 1080×1920 vertical MP4, default 45 seconds (30/45/60 selectable)
- Natural, conversational American English narration; reviewed fallback script if AI generation is unavailable
- Edge TTS neural voices: female `en-US-AriaNeural` (default), male `en-US-GuyNeural`
- Topic-specific Pexels and Pixabay stock footage; duplicate removal and relevance checks
- FFmpeg montage, burned-in English karaoke captions, and separate `output/subtitles.ass`
- Optional Whisper word-level caption timing; estimated timing fallback if unavailable
- Output resolution, audio stream, file size, and duration validation
- 1280×720 thumbnail, SEO title/description/tags, footage credits, and `output/review_manifest.json`
- Safe default: prepare only; publishing requires explicit human approval
- Verifies the OAuth account can access the configured target channel before upload

## GitHub Actions Secrets
Open **Settings → Secrets and variables → Actions → Secrets** and add:
- `PEXELS_API_KEY` — Pexels API key
- `PIXABAY_API_KEY` — Pixabay API key
- `GEMINI_API_KEY` — Gemini API key
- `FITNESS_TOKEN_JSON` — OAuth token JSON for the fitness channel only

Never put API keys or OAuth tokens in source code.

## GitHub Actions Variables
Under **Settings → Secrets and variables → Actions → Variables**:
- `FITNESS_YOUTUBE_CHANNEL_ID` = `UC7_pFbnnuMWT_US47_FD6MDA`
- `FITNESS_ALLOW_PUBLIC_UPLOAD` = `NO` until testing is complete
- `EDGE_TTS_VOICE` = `en-US-AriaNeural` (optional default)
- `GEMINI_MODEL` = `gemini-3.8-flash` if supported by your API account; otherwise use a currently available model

## First test — do not publish
1. Configure the Secrets and Variables above.
2. Open **Actions → English Fitness Shorts Bot → Run workflow**.
3. Choose `mode=prepare`, `duration=45`, `voice=female`. Use topic `3 Push-Up Mistakes to Avoid`.
4. Run the workflow and wait for it to finish.
5. Download **Artifacts → youtube-fitness-shorts**.
6. Watch and listen to `fitness_shorts.mp4` from beginning to end. Check English pronunciation, captions, relevant footage, thumbnail, and source credits.
7. Check `output/review_manifest.json`; `publish_authorized: false` is expected until you explicitly approve.

## Publishing safety
Only after you personally review and approve the video:
- Set `FITNESS_ALLOW_PUBLIC_UPLOAD=YES`.
- Run the workflow with `mode=upload`.
- Tick `confirm_upload`.
- Confirm the OAuth token can access channel `UC7_pFbnnuMWT_US47_FD6MDA`.

Scheduled runs prepare videos only; they do not publish publicly. A real stock-video render, API keys, and OAuth token must be tested in GitHub Actions before claiming the end-to-end pipeline works.

## Local Windows setup
Install Python 3.11+ and FFmpeg. From the repository root in PowerShell:
```powershell
python -m pip install -r youtube_fitnes_talyhs/requirements.txt
python youtube_fitnes_talyhs/youtube.py
```
The default mode is `prepare`, so the video is generated but not uploaded.
