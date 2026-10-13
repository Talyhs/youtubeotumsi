"""Read-only YouTube channel/video statistics using the user's local OAuth token."""
from __future__ import annotations
import json
import os
from pathlib import Path

def get_youtube_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    token_text = os.getenv("TOKEN_JSON", "").strip()
    if token_text:
        info = json.loads(token_text)
    else:
        token_file = Path(__file__).resolve().parents[1] / "token.json"
        if not token_file.exists():
            raise RuntimeError("YouTube OAuth token not found. Put token.json locally or set TOKEN_JSON.")
        info = json.loads(token_file.read_text(encoding="utf-8"))
    scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
    creds = Credentials.from_authorized_user_info(info, scopes=scopes)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)

def channel_summary():
    service = get_youtube_service()
    result = service.channels().list(part="snippet,statistics", mine=True).execute()
    items = result.get("items", [])
    if not items:
        raise RuntimeError("The OAuth account has no accessible YouTube channel.")
    item = items[0]
    return {"title": item["snippet"]["title"], "channel_id": item["id"],
            "views": int(item["statistics"].get("viewCount", 0)),
            "subscribers": int(item["statistics"].get("subscriberCount", 0)),
            "videos": int(item["statistics"].get("videoCount", 0))}

def recent_videos(limit=10):
    service = get_youtube_service()
    response = service.search().list(part="snippet", forMine=True, type="video",
                                     order="date", maxResults=min(max(int(limit),1),50)).execute()
    ids = [x["id"]["videoId"] for x in response.get("items", []) if x.get("id",{}).get("videoId")]
    if not ids:
        return []
    details = service.videos().list(part="snippet,statistics", id=",".join(ids)).execute()
    return [{"id": v["id"], "title": v["snippet"]["title"],
             "views": int(v.get("statistics", {}).get("viewCount", 0)),
             "likes": int(v.get("statistics", {}).get("likeCount", 0)),
             "comments": int(v.get("statistics", {}).get("commentCount", 0))}
            for v in details.get("items", [])]
