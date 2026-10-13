"""Explicit, user-triggered YouTube upload of the reviewed local MP4."""
from __future__ import annotations
import json
import os
from pathlib import Path

def upload_video(video_path, privacy="private", metadata_path=None, thumbnail_path=None):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("privacy must be private, unlisted or public")
    token_text = os.getenv("TOKEN_JSON", "").strip()
    if token_text:
        info = json.loads(token_text)
    else:
        token_file = Path(__file__).resolve().parents[1] / "token.json"
        if not token_file.exists():
            raise RuntimeError("OAuth token.json not found. Complete YouTube OAuth locally first.")
        info = json.loads(token_file.read_text(encoding="utf-8"))
    credentials = Credentials.from_authorized_user_info(
        info, scopes=["https://www.googleapis.com/auth/youtube.upload"])
    service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    metadata_file = Path(metadata_path) if metadata_path else Path(__file__).resolve().parents[1] / "work" / "metadata.json"
    if metadata_file.exists():
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    else:
        metadata = {"title": Path(video_path).stem, "description": "Video created with Talyhs Studio.", "tags": []}
    body = {
        "snippet": {"title": str(metadata.get("title", "Talyhs Studio video"))[:100],
                    "description": str(metadata.get("description", ""))[:4900],
                    "tags": metadata.get("tags", [])[:500], "categoryId": "27",
                    "defaultLanguage": metadata.get("language", "az")},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
    }
    request = service.videos().insert(part="snippet,status",
        body=body, media_body=MediaFileUpload(str(video_path), chunksize=8 * 1024 * 1024,
                                             resumable=True, mimetype="video/mp4"))
    response = None
    while response is None:
        _, response = request.next_chunk()
    video_id = response.get("id")
    if video_id and thumbnail_path and Path(thumbnail_path).exists():
        try:
            service.thumbnails().set(videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")).execute()
        except Exception:
            # Thumbnail upload can require extra channel eligibility; video upload remains valid.
            pass
    return {"id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
            "privacy": privacy, "title": body["snippet"]["title"]}
