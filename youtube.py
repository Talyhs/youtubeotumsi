
import asyncio
import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import edge_tts
import requests
from google import genai
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


BASE = Path(__file__).resolve().parent
WORK = BASE / "work"
WORK.mkdir(exist_ok=True)

VIDEO_FILE = BASE / "youtube_short.mp4"
AUDIO_FILE = WORK / "voiceover.mp3"
SUBTITLE_FILE = WORK / "subtitles.srt"
SCENE_FILE = WORK / "scenes.txt"
TOKEN_FILE = BASE / "token.json"

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
PEXELS_KEY = os.getenv("PEXELS_API_KEY", "").strip()
PIXABAY_KEY = os.getenv("PIXABAY_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_TEXT_MODEL", "").strip() or "gemini-2.5-flash"
TOPIC = os.getenv("VIDEO_TOPIC", "").strip() or "3 Amazing Facts About Space"
VOICE = os.getenv("EDGE_TTS_VOICE", "").strip() or "en-US-AriaNeural"
PRIVACY = os.getenv("YOUTUBE_PRIVACY_STATUS", "public").strip().lower()

if PRIVACY not in {"public", "private", "unlisted"}:
    raise RuntimeError(
        "YOUTUBE_PRIVACY_STATUS must be public, private or unlisted."
    )

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CATEGORY = "27"
HEADERS = {"User-Agent": "TalyhsYouTubeAutomation/1.0"}
TIMEOUT = 60


def run(command):
    """Run a system command and show useful errors."""
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {command[0]}\n"
            f"{result.stderr[-5000:]}"
        )
    return result.stdout


def check_configuration():
    missing = []

    if not GEMINI_KEY:
        missing.append("GEMINI_API_KEY")

    if not os.getenv("TOKEN_JSON", "").strip():
        missing.append("TOKEN_JSON")

    if not (PEXELS_KEY or PIXABAY_KEY):
        missing.append(
            "Add at least one stock-video secret: "
            "PEXELS_API_KEY or PIXABAY_API_KEY"
        )

    if missing:
        raise RuntimeError("Missing required configuration: " + ", ".join(missing))

    run(["ffmpeg", "-version"])
    run(["ffprobe", "-version"])

    try:
        token = json.loads(os.environ["TOKEN_JSON"])
    except json.JSONDecodeError as exc:
        raise RuntimeError("TOKEN_JSON is not valid JSON.") from exc

    if not token.get("refresh_token"):
        raise RuntimeError(
            "TOKEN_JSON must contain a valid OAuth refresh_token."
        )

    print("Configuration validated.")
    print("Pexels enabled:", bool(PEXELS_KEY))
    print("Pixabay enabled:", bool(PIXABAY_KEY))

def generate_text(prompt):
    client = genai.Client(api_key=GEMINI_KEY)
    last_error = None

    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )
            text = (response.text or "").strip()
            if not text:
                raise RuntimeError("Gemini returned an empty response.")
            return text
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()
            retryable = any(
                item in message
                for item in (
                    "429", "500", "502", "503", "504",
                    "resource exhausted", "temporarily unavailable",
                )
            )
            if not retryable or attempt == 4:
                raise
            time.sleep(min(2 ** (attempt + 1), 30))

    raise RuntimeError("Gemini request failed.") from last_error


def generate_script(topic):
    print("1. Generating English script...")
    prompt = f"""
Write an original English YouTube Shorts voiceover about: {topic}

Requirements:
- Around 80-120 words.
- Engaging opening and clear ending.
- Accurate, informative and natural spoken English.
- Avoid unsupported factual claims.
- No scene directions, markdown or title.
Return only the spoken script.
"""
    script = generate_text(prompt)
    print(script)
    return script


def generate_metadata(script):
    print("2. Generating metadata and stock-video search terms...")
    prompt = f"""
Create YouTube metadata for this English short video.

SCRIPT:
{script}

Return exactly five lines:
TITLE: accurate engaging title, maximum 70 characters
DESCRIPTION: two concise sentences
TAGS: 8 comma-separated relevant keywords
QUERY1: short English stock-video search query
QUERY2: short English stock-video search query

Use plain text only. Do not add extra lines.
Queries must describe visible footage, not abstract ideas.
"""
    result = generate_text(prompt)
    fields = {}

    for line in result.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip().upper()] = value.strip()

    title = fields.get("TITLE", script[:65].strip())
    description = fields.get(
        "DESCRIPTION", "Discover more in this short educational video."
    )
    tags = [
        t.strip()[:100]
        for t in fields.get("TAGS", "education,facts,learning,shorts").split(",")
        if t.strip()
    ][:15]

    queries = [
        fields.get("QUERY1", TOPIC),
        fields.get("QUERY2", TOPIC + " nature"),
        TOPIC,
    ]
    queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))
    return title[:100], description, tags, queries[:3]


def search_pexels(query):
    response = requests.get(
        "https://api.pexels.com/v1/videos/search",
        headers={"Authorization": PEXELS_KEY},
        params={
            "query": query,
            "orientation": "landscape",
            "size": "medium",
            "per_page": 8,
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    results = []

    for video in response.json().get("videos", []):
        files = sorted(
            video.get("video_files", []),
            key=lambda f: (
                0 if f.get("file_type") == "video/mp4" else 1,
                abs((f.get("width") or 0) - 1920),
            ),
        )
        file = next(
            (
                f for f in files
                if f.get("link")
                and f.get("file_type") == "video/mp4"
                and (f.get("width") or 0) >= 640
            ),
            None,
        )
        if not file:
            continue

        user = video.get("user") or {}
        results.append({
            "source": "Pexels",
            "url": file["link"],
            "page": video.get("url", "https://www.pexels.com"),
            "creator": user.get("name", "Unknown"),
            "creator_url": user.get("url", "https://www.pexels.com"),
            "id": str(video.get("id", "")),
        })
    return results


def search_pixabay(query):
    response = requests.get(
        "https://pixabay.com/api/videos/",
        params={
            "key": PIXABAY_KEY,
            "q": query,
            "safesearch": "true",
            "per_page": 8,
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    results = []

    for video in response.json().get("hits", []):
        variants = video.get("videos") or {}
        file = variants.get("large") or variants.get("medium") or variants.get("small")
        if not file or not file.get("url"):
            continue

        user = video.get("user", "Unknown")
        results.append({
            "source": "Pixabay",
            "url": file["url"],
            "page": video.get("pageURL", "https://pixabay.com"),
            "creator": user,
            "creator_url": "https://pixabay.com/users/" + str(user) + "/",
            "id": str(video.get("id", "")),
        })
    return results


def download_file(url, destination):
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise RuntimeError("Refusing non-HTTPS media URL.")

    with requests.get(
        url, stream=True, timeout=(20, 120), headers=HEADERS
    ) as response:
        response.raise_for_status()
        with open(destination, "wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    output.write(chunk)

    if not destination.exists() or destination.stat().st_size < 10_000:
        destination.unlink(missing_ok=True)
        raise RuntimeError("Downloaded video is empty or too small.")

    # Confirm the downloaded file is readable by FFmpeg.
    run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(destination),
    ])



def collect_clips(queries, wanted=5):
    print("3. Searching available stock video providers...")

    providers = []

    if PEXELS_KEY:
        providers.append(search_pexels)

    if PIXABAY_KEY:
        providers.append(search_pixabay)

    if not providers:
        raise RuntimeError(
            "No stock video provider configured. "
            "Add PEXELS_API_KEY or PIXABAY_API_KEY to GitHub Secrets."
        )

    candidates = []
    seen = set()

    for query in queries:
        for search in providers:
            try:
                results = search(query)
                print(
                    f"{search.__name__}: "
                    f"{len(results)} results for {query!r}"
                )

                for item in results:
                    key = (item["source"], item["id"] or item["url"])
                    if key not in seen:
                        seen.add(key)
                        candidates.append(item)

            except Exception as exc:
                print(
                    f"Provider {search.__name__} failed: {exc}. "
                    "Trying the next provider."
                )
                continue

    if not candidates:
        raise RuntimeError(
            "Neither configured provider returned usable videos. "
            "Check API keys, quotas and network access."
        )

    selected = []

    for item in candidates:
        path = WORK / f"stock_{len(selected) + 1}.mp4"

        try:
            print("Downloading:", item["source"], item["page"])
            download_file(item["url"], path)
            item["file"] = path
            selected.append(item)

            if len(selected) >= wanted:
                break

        except Exception as exc:
            print("Download failed; trying another clip:", exc)

    if not selected:
        raise RuntimeError(
            "Videos were found, but none could be downloaded."
        )

    print(f"Selected {len(selected)} stock video(s).")
    return selected


def create_voice_and_subtitles(script):
    print("4. Generating Edge-TTS neural voice and timed captions...")

    async def synthesize():
        communicate = edge_tts.Communicate(
            script,
            VOICE,
            rate="+0%",
        )
        boundaries = []

        with open(AUDIO_FILE, "wb") as audio:
            async for item in communicate.stream():
                if item["type"] == "audio":
                    audio.write(item["data"])
                elif item["type"] == "WordBoundary":
                    boundaries.append({
                        "start": item["offset"] / 10_000_000,
                        "duration": item["duration"] / 10_000_000,
                        "text": item["text"],
                    })
        return boundaries

    boundaries = asyncio.run(synthesize())

    if not AUDIO_FILE.exists() or AUDIO_FILE.stat().st_size == 0:
        raise RuntimeError("Edge-TTS did not create an audio file.")
    if not boundaries:
        raise RuntimeError("Edge-TTS returned no word timing data.")

    def stamp(seconds):
        ms = max(0, int(seconds * 1000))
        hours, ms = divmod(ms, 3_600_000)
        minutes, ms = divmod(ms, 60_000)
        seconds, ms = divmod(ms, 1000)
        return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"

    # Group words into short readable captions using actual speech timings.
    groups = []
    current = []

    for word in boundaries:
        if current and (
            len(current) >= 7
            or word["start"] - (current[-1]["start"] + current[-1]["duration"]) > 0.65
        ):
            groups.append(current)
            current = []
        current.append(word)

    if current:
        groups.append(current)

    lines = []
    for index, group in enumerate(groups, 1):
        start = group[0]["start"]
        end = group[-1]["start"] + group[-1]["duration"]
        text = " ".join(w["text"] for w in group)
        lines.extend([
            str(index),
            f"{stamp(start)} --> {stamp(max(start + 0.2, end))}",
            text,
            "",
        ])

    SUBTITLE_FILE.write_text("\n".join(lines), encoding="utf-8")
    return get_audio_duration()


def get_audio_duration():
    value = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(AUDIO_FILE),
    ]).strip()
    duration = float(value)
    if duration <= 0:
        raise RuntimeError("Invalid audio duration.")
    return duration


def make_video(clips, duration):
    print("5. Editing stock footage, voice and subtitles...")
    scene_duration = duration / len(clips)
    normalized = []

    for index, clip in enumerate(clips):
        output = WORK / f"scene_{index:02}.mp4"
        length = scene_duration
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-stream_loop", "-1", "-i", str(clip["file"]),
            "-t", f"{length:.3f}",
            "-vf",
            "scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080,fps=30,setsar=1",
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output),
        ])
        normalized.append(output)

    concat_file = WORK / "concat.txt"
    concat_file.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in normalized),
        encoding="utf-8",
    )

    # Quote the subtitle path safely for FFmpeg's filter syntax.
    subtitle_path = SUBTITLE_FILE.resolve().as_posix()
    subtitle_path = subtitle_path.replace("\\", r"\\").replace(":", r"\:")
    subtitle_path = subtitle_path.replace("'", r"\'")

    filter_arg = (
        f"subtitles='{subtitle_path}':"
        "force_style='FontName=DejaVu Sans,FontSize=18,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=55'"
    )

    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-i", str(AUDIO_FILE),
        "-vf", filter_arg,
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", f"{duration:.3f}",
        "-r", "30",
        "-c:v", "libx264", "-preset", "medium",
        "-crf", "21", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        str(VIDEO_FILE),
    ])

    if not VIDEO_FILE.exists() or VIDEO_FILE.stat().st_size == 0:
        raise RuntimeError("Final MP4 was not created.")


def build_credits(clips):
    lines = [
        "",
        "STOCK FOOTAGE CREDITS",
        "Footage is used subject to the respective platform's license.",
        "",
    ]
    for clip in clips:
        lines.append(
            f'{clip["source"]} | Creator: {clip["creator"]} | '
            f'Source: {clip["page"]} | Creator page: {clip["creator_url"]}'
        )

    lines.extend([
        "",
        "Stock platforms: https://www.pexels.com/ and https://pixabay.com/",
    ])
    return "\n".join(lines)


def get_youtube_service():
    print("6. Connecting to YouTube via OAuth...")
    token_json = os.environ.get("TOKEN_JSON", "").strip()

    if not token_json:
        raise RuntimeError("TOKEN_JSON secret is missing.")

    token_path = WORK / "token.json"
    token_path.write_text(token_json, encoding="utf-8")

    credentials = Credentials.from_authorized_user_file(
        str(token_path),
        SCOPES,
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    elif not credentials.valid:
        raise RuntimeError(
            "OAuth token is invalid or has no refresh token. "
            "Regenerate TOKEN_JSON with offline access."
        )

    return build(
        "youtube", "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def upload_video(title, description, tags, clips):
    print("7. Uploading MP4 to YouTube...")
    youtube = get_youtube_service()

    full_description = (
        description.strip()
        + "\n\n"
        + build_credits(clips)
        + "\n\n#Shorts"
    )

    body = {
        "snippet": {
            "title": title[:100],
            "description": full_description[:5000],
            "tags": tags[:15],
            "categoryId": YOUTUBE_CATEGORY,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": PRIVACY,
            "selfDeclaredMadeForKids": False,
        },
    }

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(
            str(VIDEO_FILE),
            mimetype="video/mp4",
            resumable=True,
        ),
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    print("Upload completed:", f"https://www.youtube.com/watch?v={video_id}")
    print("Requested visibility:", PRIVACY)
    return video_id


def main():
    print("========================================")
    print(" TALYHS / YOUTUBE AUTOMATION")
    print("========================================")
    print("Topic:", TOPIC)
    print("Gemini model:", MODEL)

    check_configuration()
    script = generate_script(TOPIC)
    title, description, tags, queries = generate_metadata(script)
    clips = collect_clips(queries, wanted=5)
    duration = create_voice_and_subtitles(script)
    make_video(clips, duration)
    upload_video(title, description, tags, clips)

    print("Final MP4:", VIDEO_FILE)
    print("Subtitles:", SUBTITLE_FILE)


if __name__ == "__main__":
    main()
