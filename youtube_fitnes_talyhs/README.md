# youtube_fitnes_talyhs — English Fitness Shorts Automation

This folder creates English-language fitness Shorts for the separate second YouTube channel.

## Features
- Vertical MP4 output at 1080×1920, default 45 seconds (configurable from 30–60 seconds)
- Original English fitness scripts with a reviewed fallback if Gemini is unavailable
- English quality gate: natural US English, grammar/spelling guidance, topic-specific SEO search terms, and a second AI rewrite when narration length is outside the selected runtime
- Runtime-aware narration targets: approximately 52–72 words (30s), 82–105 words (45s), or 112–135 words (60s); rejected scripts use a duration-matched fallback
- Pexels and Pixabay stock footage search and downloads
- Microsoft Edge neural text-to-speech using `en-US-AriaNeural` (natural US English female voice)
- FFmpeg montage and burned-in English karaoke captions: large bold text, dark outline/shadow, short readable phrase beats, and moving yellow word highlighting synchronized across the narration
- A separate `output/subtitles.ass` caption file is saved with the generated video for review and future style tweaks
- English title, description, hashtags, and stock-footage credits
- Verifies the OAuth account can access the configured target channel before upload
- Scheduled runs prepare videos only; public upload remains blocked by default

## English script quality
The generator asks for idiomatic, grammatically correct American English and checks that narration length matches the selected 30/45/60-second runtime. If the generated script is outside the target word range, it requests one revision; if the result still fails validation or the AI service is unavailable, it uses a safety-conscious fallback matched to the selected duration. Always listen to the generated audio and review captions before publishing.

## Voice
Default: `en-US-AriaNeural` — English (United States), neural female voice.
Alternatives: `en-US-JennyNeural` for another female voice, or `en-US-ChristopherNeural` for a male voice. Set the GitHub Actions Variable `EDGE_TTS_VOICE` to change it.

This uses Edge TTS, a neural voice service requiring an internet connection. It is not ElevenLabs, and voice availability can change.

## GitHub Actions
Workflow: [English Fitness Shorts Bot](../.github/workflows/fitness-shorts.yml)

The schedule attempts three video-preparation runs daily at 07:30, 12:00, and 18:30 Turkey time (UTC+3). GitHub scheduled workflows may be delayed. Videos are saved in the run's `youtube-fitness-shorts` artifact ZIP. Scheduled runs do not publish automatically.

## GitHub Secrets
Open **Settings → Secrets and variables → Actions → Secrets** and add:
- `PEXELS_API_KEY`
- `PIXABAY_API_KEY`
- `GEMINI_API_KEY` (optional; enables AI script generation)
- `FITNESS_TOKEN_JSON` (OAuth token JSON for the second channel; never commit it to the repository)

The OAuth token should include:
- `https://www.googleapis.com/auth/youtube.upload`
- `https://www.googleapis.com/auth/youtube.readonly`

## GitHub Variables
Open **Settings → Secrets and variables → Actions → Variables** and add:
- `FITNESS_YOUTUBE_CHANNEL_ID` = `UC7_pFbnnuMWT_US47_FD6MDA`
- `FITNESS_ALLOW_PUBLIC_UPLOAD` = `NO` until testing is complete
- `EDGE_TTS_VOICE` = `en-US-AriaNeural`
- `GEMINI_MODEL` = `gemini-2.5-flash`

## First test
1. Add the API keys and Variables.
2. Open GitHub → **Actions → English Fitness Shorts Bot → Run workflow**.
3. Choose `prepare` and click **Run workflow**.
4. When it finishes, download **Artifacts → youtube-fitness-shorts** and check the English narration, video relevance, subtitles, and credits.
5. Verify the OAuth token belongs to the intended second channel.
6. Only after testing, set `FITNESS_ALLOW_PUBLIC_UPLOAD=YES` and manually choose `upload`.

## Local Windows setup
Install Python 3.11+ and FFmpeg, then run in PowerShell:
```powershell
cd youtube_fitnes_talyhs
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:PEXELS_API_KEY = "YOUR_API_KEY"
$env:PIXABAY_API_KEY = "YOUR_API_KEY"
$env:EDGE_TTS_VOICE = "en-US-AriaNeural"
$env:PUBLISH_MODE = "prepare"
python youtube.py
```

Never store real API keys or OAuth tokens in source code. Check stock footage licensing and the accuracy of fitness information before publishing. This content is general education, not medical advice.
