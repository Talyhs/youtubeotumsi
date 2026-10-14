# youtube_fitnes_talyhs — English Fitness Shorts

This project generates English-language fitness Shorts (30–60 seconds) using stock footage, neural voice, subtitles, and optional YouTube upload.

## Features
- Vertical 1080×1920 MP4, default 45 seconds
- English script generation with Gemini when configured; safe built-in fallback script otherwise
- Stock footage search/download from Pexels and Pixabay
- Neural English narration using `edge-tts` (`en-US-GuyNeural` by default)
- FFmpeg montage, burned-in subtitles, MP4 output
- SEO title, description, hashtags, and stock source credits
- YouTube OAuth upload with target channel verification before upload
- Default `prepare` mode; public upload requires explicit repository variable

## GitHub setup
Add repository **Secrets** under Settings → Secrets and variables → Actions:
- `PEXELS_API_KEY` — recommended
- `PIXABAY_API_KEY` — recommended
- `GEMINI_API_KEY` — optional, for generated scripts
- `TOKEN_JSON` — complete OAuth authorized-user token JSON; never commit this file

Add repository **Variables**:
- `YOUTUBE_CHANNEL_ID` — exact channel ID that the OAuth credentials should access
- `ALLOW_PUBLIC_UPLOAD` — keep unset/`NO` until the generated video and OAuth channel are tested; set to `YES` only when ready for public uploads

The OAuth token must include both scopes:
- `https://www.googleapis.com/auth/youtube.upload`
- `https://www.googleapis.com/auth/youtube.readonly`

## First run
1. Push this folder to a new GitHub repository named `youtube_fitnes_talyhs`.
2. Add the secrets and channel variable above.
3. Open Actions → English Fitness Shorts Bot → Run workflow.
4. Choose `prepare`. Download the `youtube-fitness-shorts` artifact and inspect the MP4, voice, subtitles, and credits.
5. Only after testing, set `ALLOW_PUBLIC_UPLOAD=YES` and manually run with `upload`.

The scheduled run is intentionally `prepare` only. It does not auto-publish publicly. The cron is 16:00 UTC (20:00 in Azerbaijan during UTC+4), but schedule timing can be delayed by GitHub Actions.

## Local Windows setup
Install Python 3.11+ and FFmpeg, then in PowerShell:
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:PEXELS_API_KEY = "your-key"
$env:PIXABAY_API_KEY = "your-key"
$env:GEMINI_API_KEY = "your-key" # optional
$env:PUBLISH_MODE = "prepare"
python youtube.py
```
Do not paste real keys into source files or commit them to GitHub. For upload, also set `TOKEN_JSON`, `YOUTUBE_CHANNEL_ID`, and `ALLOW_PUBLIC_UPLOAD=YES` only after checking the channel and OAuth scopes.

## Important
- Check the current Pexels/Pixabay license and API terms for every clip; adding credits does not override license restrictions.
- Review fitness claims before publishing. This is general education, not medical advice.
- `edge-tts` availability/voice options may change. If the chosen voice is unavailable, change `EDGE_TTS_VOICE` to another supported English voice.
- This is a starter implementation; validate generated videos and OAuth setup before enabling public uploads.
