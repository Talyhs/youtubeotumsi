
import os
import textwrap
from pathlib import Path

from google import genai
from google.genai import types
from gtts import gTTS
from PIL import Image

from moviepy.editor import (
    AudioFileClip,
    ImageClip,
    TextClip,
    CompositeVideoClip,
)

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# IMPORTANT: GitHub variables may exist but be empty.
# "or" ensures that a default model is always selected.


TEXT_MODEL = (
    os.environ.get("GEMINI_TEXT_MODEL", "").strip()
    or "gemini-3.8-flash"
)

IMAGE_MODEL = (
    os.environ.get("GEMINI_IMAGE_MODEL", "").strip()
    or "gemini-2.5-flash-image"
)

TOPIC = (
    os.environ.get("VIDEO_TOPIC")
    or "3 Amazing Facts About Space"
).strip() or "3 Amazing Facts About Space"

BACKGROUND_IMAGE = BASE_DIR / "background.png"
AUDIO_FILE = BASE_DIR / "voiceover.mp3"
VIDEO_FILE = BASE_DIR / "youtube_short.mp4"
TEMP_IMAGE = BASE_DIR / "background_video.jpg"

CLIENT_SECRETS_FILE = BASE_DIR / "client_secrets.json"
TOKEN_FILE = BASE_DIR / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload"
]

CATEGORY_ID = "28"

PRIVACY_STATUS = (
    os.environ.get("YOUTUBE_PRIVACY_STATUS") or "public"
).strip().lower()

if PRIVACY_STATUS not in ("public", "private", "unlisted"):
    PRIVACY_STATUS = "public"


# =========================================================
# GEMINI CLIENT
# =========================================================

def get_gemini_client():
    """Create a Gemini API client."""

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Add it under "
            "GitHub Settings > Secrets and variables > Actions."
        )

    return genai.Client(api_key=api_key)


TEXT_MODEL = (
    os.environ.get("GEMINI_TEXT_MODEL", "").strip()
    or "gemini-3.8-flash"
)


# =========================================================
# GENERATE ENGLISH SCRIPT
# =========================================================

def generate_script(topic):
    print("1. Generating English script...")

    prompt = f"""
Write an engaging YouTube Shorts voiceover script in English.

TOPIC: {topic}

Requirements:
- Approximately 40-80 words.
- Start with an interesting hook.
- Use natural spoken English.
- Make it informative and entertaining.
- Suitable for a general international audience.
- No emojis.
- No title or scene directions.
- Return only the words to be spoken.
"""

    script = generate_text(prompt)

    print("\n========== SCRIPT ==========")
    print(script)
    print("============================\n")

    return script


# =========================================================
# GENERATE VIDEO METADATA
# =========================================================

def generate_video_metadata(script):
    print("2. Generating video title and metadata...")

    prompt = f"""
Create metadata for a YouTube Shorts video.

SCRIPT:
{script}

Return exactly these four lines:
TITLE: a catchy accurate title under 70 characters
DESCRIPTION: a concise description relevant to the script
TAGS: 8 relevant comma-separated keywords
IMAGE IDEA: a detailed visual idea for the background image

Rules:
- English only.
- No misleading claims.
- Do not include extra commentary.
- The image idea must match the script.
"""

    result = generate_text(prompt)
    fields = {}

    for line in result.splitlines():
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        fields[key.strip().upper()] = value.strip()

    title = fields.get("TITLE", "").strip()
    description = fields.get("DESCRIPTION", "").strip()
    tags_text = fields.get("TAGS", "").strip()
    image_idea = fields.get("IMAGE IDEA", "").strip()

    if not title:
        title = script.split(".")[0][:65].strip()
        if not title:
            title = "Amazing Facts You Should Know"

    if not description:
        description = (
            "Discover something amazing in this short video."
        )

    tags = [
        tag.strip()
        for tag in tags_text.split(",")
        if tag.strip()
    ]

    if not tags:
        tags = ["facts", "education", "science", "shorts"]

    tags = tags[:15]

    if "#Shorts" not in description:
        description += "\n\n#Shorts"

    if not image_idea:
        image_idea = (
            "A cinematic, realistic visual representation of: "
            + script[:500]
        )

    print("Title:", title)
    print("Image idea:", image_idea)

    return title, description, tags, image_idea


# =========================================================
# GENERATE VOICEOVER
# =========================================================

def create_voice(script):
    print("3. Generating English voiceover...")

    tts = gTTS(text=script, lang="en", slow=False)
    tts.save(str(AUDIO_FILE))

    if not AUDIO_FILE.is_file() or AUDIO_FILE.stat().st_size == 0:
        raise RuntimeError("Voiceover file was not created.")

    print("Voiceover saved:", AUDIO_FILE.name)
    return str(AUDIO_FILE)


# =========================================================
# GENERATE TOPIC-SPECIFIC AI BACKGROUND
# =========================================================

def generate_background_image(script, title, image_idea):
    print("4. Generating AI background image...")

    client = get_gemini_client()

    model = (
        os.environ.get("GEMINI_IMAGE_MODEL")
        or "gemini-2.5-flash-image"
    ).strip() or "gemini-2.5-flash-image"

    print("Using Gemini image model:", model)

    prompt = f"""
Generate an actual image for a vertical YouTube Shorts video.

TITLE:
{title}

SCRIPT:
{script}

VISUAL CONCEPT:
{image_idea}

Image requirements:
- Portrait 9:16 composition.
- Match the topic and script accurately.
- Strong central subject and cinematic lighting.
- High visual quality and clear details.
- Leave some uncluttered space for subtitles.
- No text, letters, captions, logos or watermarks.
- Return an image, not a written description.
"""

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio="9:16",
                image_size="1K",
            ),
        ),
    )

    for part in (response.parts or []):
        if getattr(part, "inline_data", None) is None:
            continue

        image = part.as_image()

        if image is None:
            continue

        image.save(str(BACKGROUND_IMAGE))

        # Verify that the output is a valid image.
        with Image.open(BACKGROUND_IMAGE) as check:
            check.verify()

        print("AI background saved:", BACKGROUND_IMAGE.name)
        return str(BACKGROUND_IMAGE)

    raise RuntimeError(
        "Gemini did not return an image. Check whether the image "
        "model is available to your API key, and check API quota."
    )


# =========================================================
# CREATE VERTICAL VIDEO
# =========================================================

def create_video(audio_file, script):
    print("5. Creating vertical YouTube Shorts video...")

    if not BACKGROUND_IMAGE.is_file():
        raise FileNotFoundError(
            f"Background image is missing: {BACKGROUND_IMAGE}"
        )

    audio = None
    background = None
    text_clip = None
    video = None

    try:
        audio = AudioFileClip(audio_file)
        duration = audio.duration

        if not duration or duration <= 0:
            raise RuntimeError("Voiceover duration is invalid.")

        # Convert to RGB JPEG for MoviePy compatibility.
        with Image.open(BACKGROUND_IMAGE) as img:
            img = img.convert("RGB")

            target_ratio = 9 / 16
            current_ratio = img.width / img.height

            if current_ratio > target_ratio:
                new_width = int(img.height * target_ratio)
                left = (img.width - new_width) // 2
                img = img.crop(
                    (left, 0, left + new_width, img.height)
                )
            else:
                new_height = int(img.width / target_ratio)
                top = (img.height - new_height) // 2
                img = img.crop(
                    (0, top, img.width, top + new_height)
                )

            img = img.resize((1080, 1920))
            img.save(TEMP_IMAGE, quality=95)

        background = (
            ImageClip(str(TEMP_IMAGE))
            .set_duration(duration)
        )

        # Add readable subtitles. If ImageMagick cannot render text,
        # continue with the background and voiceover.
        try:
            wrapped = textwrap.fill(script, width=30)

            text_clip = (
                TextClip(
                    wrapped,
                    fontsize=52,
                    color="white",
                    bg_color="black",
                    size=(940, None),
                    method="caption",
                    align="center",
                )
                .set_position(("center", "center"))
                .set_duration(duration)
            )

            video = CompositeVideoClip(
                [background, text_clip],
                size=(1080, 1920),
            )

        except Exception as error:
            print("Subtitle rendering failed:", str(error))
            print("Continuing without subtitles.")

            video = CompositeVideoClip(
                [background],
                size=(1080, 1920),
            )

        video = video.set_audio(audio)

        video.write_videofile(
            str(VIDEO_FILE),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=2,
            logger="bar",
        )

        if not VIDEO_FILE.is_file() or VIDEO_FILE.stat().st_size == 0:
            raise RuntimeError("Video output was not created.")

        print("Video saved:", VIDEO_FILE.name)
        return str(VIDEO_FILE)

    finally:
        # Close resources even when video creation fails.
        if video is not None:
            video.close()

        if text_clip is not None:
            text_clip.close()

        if background is not None:
            background.close()

        if audio is not None:
            audio.close()


# =========================================================
# YOUTUBE AUTHENTICATION
# =========================================================

def get_youtube_service():
    print("6. Connecting to YouTube...")

    credentials = None

    # Prefer the secret name used by this workflow.
    token_json = (
        os.environ.get("TOKEN_JSON")
        or os.environ.get("YOUTUBE_TOKEN_JSON")
    )

    if token_json:
        TOKEN_FILE.write_text(token_json, encoding="utf-8")

    if TOKEN_FILE.is_file():
        credentials = Credentials.from_authorized_user_file(
            str(TOKEN_FILE),
            SCOPES,
        )

    if credentials and credentials.expired and credentials.refresh_token:
        print("Refreshing YouTube OAuth token...")
        credentials.refresh(Request())

    elif not credentials or not credentials.valid:
        # GitHub Actions cannot interactively open a browser to sign in.
        if os.environ.get("GITHUB_ACTIONS") == "true":
            raise RuntimeError(
                "YouTube OAuth credentials are missing or invalid. "
                "Create a valid token.json with a refresh token locally, "
                "then save its full JSON as the TOKEN_JSON GitHub secret."
            )

        if not CLIENT_SECRETS_FILE.is_file():
            raise FileNotFoundError(
                "client_secrets.json is missing. Configure Google OAuth."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRETS_FILE),
            SCOPES,
        )

        credentials = flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent",
        )

    # Save updated credentials locally.
    TOKEN_FILE.write_text(
        credentials.to_json(),
        encoding="utf-8",
    )

    return build(
        "youtube",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


# =========================================================
# UPLOAD VIDEO
# =========================================================

def upload_to_youtube(video_file, title, description, tags):
    print("7. Uploading video to YouTube...")

    youtube = get_youtube_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": CATEGORY_ID,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_file,
        mimetype="video/mp4",
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None

    while response is None:
        status, response = request.next_chunk()

        if status:
            progress = int(status.progress() * 100)
            print(f"Upload progress: {progress}%")

    video_id = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    print("\n================================")
    print("VIDEO UPLOADED SUCCESSFULLY")
    print("Title:", title)
    print("Video ID:", video_id)
    print("URL:", video_url)
    print("================================")

    return video_id


# =========================================================
# MAIN PIPELINE
# =========================================================

def main():
    print()
    print("====================================")
    print("     ENGLISH YOUTUBE AUTOMATION")
    print("====================================")
    print()

    print("Topic:", TOPIC)
    print("Text model:", TEXT_MODEL)
    print("Image model:", IMAGE_MODEL)

    script = generate_script(TOPIC)

    title, description, tags, image_idea = (
        generate_video_metadata(script)
    )

    audio_file = create_voice(script)

    generate_background_image(
        script,
        title,
        image_idea,
    )

    video_file = create_video(
        audio_file,
        script,
    )

    upload_to_youtube(
        video_file,
        title,
        description,
        tags,
    )

    print()
    print("====================================")
    print("          PIPELINE COMPLETE")
    print("====================================")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print()
        print("ERROR: YouTube automation failed.")
        print(f"{type(error).__name__}: {error}")
        raise
