# Talyhs Studio — web control panel

## What it does
- Password-protected Streamlit control panel.
- Sends topic, language, duration, video format, voice, stock provider, subtitle, thumbnail, SEO and visibility selections to GitHub Actions.
- Displays recent workflow runs and links to their logs/artifacts.
- GitHub token stays on the server, not in the browser.

## Deploy on Render
1. Create a new Web Service from this repository.
2. Render detects `render.yaml`.
3. Set `DASHBOARD_PASSWORD` to a strong unique password.
4. Set `GH_TOKEN` to a fine-grained GitHub token scoped only to this repository, with Actions: Read and write. Keep it only in Render environment variables.
5. Deploy. Render will provide the live URL.

## Important
- The workflow must contain a `workflow_dispatch` trigger with matching input names.
- OAuth/API secrets for video generation belong in GitHub Actions Secrets.
- A successful workflow dispatch means the job was queued, not that a video was successfully rendered or uploaded.
- Scheduled publishing and thumbnail upload require the pipeline extensions and credentials described in the project README.
