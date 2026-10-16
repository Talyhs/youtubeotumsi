# Talyhs Studio — Multi-channel panel setup

## Channels
The sidebar selector controls which workflow the panel dispatches:
- **Əsas YouTube kanalı** → `.github/workflows/main.yml`
- **Fitness Shorts · English** → `.github/workflows/fitness-shorts.yml`

Fitness production accepts a topic, 30/45/60 second duration and female/male/automatic English neural voice. The default action is **prepare**, which creates the video without uploading it.

## Render environment variables
Keep secrets in Render's Environment settings, never in the repository:
- `DASHBOARD_PASSWORD`: a long, unique panel password.
- `GH_TOKEN`: a fine-grained GitHub token limited to `Talyhs/youtubeotumsi` with Actions read/write permissions.
- `GITHUB_REPOSITORY=Talyhs/youtubeotumsi`
- `GITHUB_WORKFLOW_FILE=main.yml`
- `GITHUB_BRANCH=main`
- `YOUTUBE_TOKEN_JSON`: optional OAuth JSON for read-only main-channel analytics.
- `FITNESS_YOUTUBE_TOKEN_JSON`: optional OAuth JSON for read-only fitness-channel analytics.
- `FITNESS_YOUTUBE_CHANNEL_ID=UC7_pFbnnuMWT_US47_FD6MDA`

The video workflows separately require their GitHub Actions secrets (Pexels/Pixabay and the channel's OAuth token). The fitness workflow uses `FITNESS_TOKEN_JSON` and will refuse upload unless `FITNESS_ALLOW_PUBLIC_UPLOAD=YES`.

## Safe verification
1. Merge this pull request only after reviewing the changes and CI result.
2. Deploy the updated branch to Render.
3. Sign in, select **Fitness Shorts · English**, enter a test topic and choose **Yalnız hazırla**.
4. Open GitHub Actions → **English Fitness Shorts Bot** and confirm the run succeeds.
5. Download the `youtube-fitness-shorts` artifact and inspect the MP4, narration and subtitles.
6. Keep upload disabled until the second channel ID and OAuth token are verified. The current fitness uploader publishes publicly; the panel requires an explicit confirmation and the workflow additionally requires `FITNESS_ALLOW_PUBLIC_UPLOAD=YES`.

## Important limitations
- This panel sends jobs to GitHub Actions; it does not itself render videos in the browser.
- Calendar entries are planning records and must be dispatched manually; the calendar does not yet start a job automatically at its planned time.
- The live Render deployment and full end-to-end video output have not been verified by this code change.
