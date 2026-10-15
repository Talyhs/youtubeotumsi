# Talyhs YouTube Studio — Windows + Web

## Included
- Dark Streamlit web panel: production controls, job status, GitHub Actions logs, thumbnail builder, planning calendar and YouTube channel statistics.
- PySide6 Windows desktop app and SQLite history/calendar from the Windows Studio branch.
- Windows build workflow which produces a ZIP artifact containing the desktop EXE and engine bundle.
- Existing YouTube video workflow remains the production engine.

## Web panel on Render
1. Open the existing Render service for talyhs-youtube-studio, or create a new Web Service from this repository.
2. Deploy the branch after reviewing/merging its pull request.
3. Set these environment variables in Render:
   - DASHBOARD_PASSWORD: a long, unique panel password.
   - GH_TOKEN: fine-grained GitHub token limited to Talyhs/youtubeotumsi with Actions read/write. It also needs Actions read access to retrieve logs.
   - GITHUB_REPOSITORY=Talyhs/youtubeotumsi
   - GITHUB_WORKFLOW_FILE=main.yml
   - GITHUB_BRANCH=main
   - YOUTUBE_TOKEN_JSON: optional OAuth JSON with youtube.readonly scope, only if channel analytics are needed.
4. Never paste secrets into source code or commit them. If a token has been exposed, revoke and recreate it.
5. Open the Render service URL and sign in with DASHBOARD_PASSWORD.

Render free filesystem may be ephemeral; calendar entries stored in SQLite may reset after a redeploy/restart unless persistent storage is configured. The calendar currently saves ideas and lets you dispatch them manually; it does not autonomously start jobs at the planned time.

## Windows desktop EXE
1. Open GitHub Actions in this repository.
2. Choose “Build Talyhs Studio for Windows”.
3. Select “Run workflow” on the release branch.
4. When the run succeeds, open its Artifacts section and download TalyhsStudio-Windows.
5. Extract the ZIP and launch TalyhsStudio.exe. Keep the engine directory beside it.
6. Install FFmpeg and ensure ffmpeg and ffprobe work in Command Prompt. Put local .env and token.json beside the app only if needed. Never commit them.

The EXE must be built on Windows. GitHub Actions provides a Windows runner for this purpose.

## Production workflow inputs
The web panel submits the existing main.yml inputs: topic, language, duration, video_format, voice, voice_provider, stock_sources, subtitles, thumbnail, seo, privacy and publish. Keep these names aligned with .github/workflows/main.yml.

## YouTube analytics
The OAuth JSON must have the https://www.googleapis.com/auth/youtube.readonly scope. A token authorized only for upload may not permit analytics. Analytics are read-only; uploading a video is controlled separately by the GitHub workflow.

## Safe first test
Use publish mode “Yalnız hazırla” and privacy “private”. Verify the final MP4 and logs before choosing public upload. The dashboard does not claim a video has uploaded merely because GitHub accepted a workflow dispatch.
