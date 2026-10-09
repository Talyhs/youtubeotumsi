
import os
import textwrap
import re

from google import genai
from google.genai import types
from gtts import gTTS
from PIL import Image

from moviepy.editor import (
    AudioFileClip,
    ImageClip,
    TextClip,
    CompositeVideoClip
)

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# =========================================================
# CONFIGURATION
# =========================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

TEXT_MODEL = os.environ.get(
    "GEMINI_TEXT_MODEL",
    "gemini-3.8-flash"
)

IMAGE_MODEL = os.environ.get(
    "GEMINI_IMAGE_MODEL",
    "gemini-3.1-flash-image"
)

TOPIC = os.environ.get(
    "VIDEO_TOPIC",
    "3 Amazing Facts About Space"
)

BACKGROUND_IMAGE = "background.png"
AUDIO_FILE = "voiceover.mp3"
VIDEO_FILE = "youtube_short.mp4"

CLIENT_SECRETS_FILE = "client_secrets.json"
TOKEN_FILE = "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload"
]

VIDEO_TITLE = ""
VIDEO_DESCRIPTION = ""
VIDEO_TAGS = []

CATEGORY_ID = "28"
PRIVACY_STATUS = "public"


# =========================================================
# GEMINI CLIENT
# =========================================================

def get_gemini_client():
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is missing. "
            "Add it to GitHub Actions Secrets."
        )

    return genai.Client(api_key=GEMINI_API_KEY)


# =========================================================
# STEP 1 — GENERATE ENGLISH SCRIPT
# =========================================================

def generate_script(topic):

    print("1. Generating English script...")

    client = get_gemini_client()

    prompt = f"""
Create a YouTube Shorts script in English.

TOPIC: {topic}

Requirements:
- 30-50 words.
- Start with a strong hook.
- Make it exciting and easy to understand.
- Use natural spoken English.
- Suitable for an international audience.
- No emojis.
- Do not write a title.
- Do not say hello.
- Return only the spoken script.
"""

    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=prompt
    )

    script = (response.text or "").strip()

    if not script:
        raise RuntimeError("Gemini returned an empty script.")

    print("\n========== SCRIPT ==========")
    print(script)
    print("============================\n")

    return script


# =========================================================
# STEP 2 — GENERATE TITLE, DESCRIPTION AND TAGS
# =========================================================

def generate_video_metadata(script):

    print("2. Generating video title and metadata...")

    client = get_gemini_client()

    prompt = f"""
Create YouTube Shorts metadata for this English video script.

SCRIPT:
{script}

Return exactly these four lines:
TITLE: a catchy, accurate title under 70 characters
DESCRIPTION: a short, relevant description
TAGS: 8 relevant comma-separated keywords
IMAGE IDEA: a detailed visual concept for the video background

Rules:
- Use English.
- Do not use misleading claims.
- Do not add explanations outside these four lines.
- The image idea must match the script.
"""

    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=prompt
    )

    result = (response.text or "").strip()

    if not result:
        raise RuntimeError("Metadata generation failed.")

    fields = {}

    for line in result.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip().upper()] = value.strip()

    title = fields.get("TITLE", "").strip()
    description = fields.get("DESCRIPTION", "").strip()
    tags_text = fields.get("TAGS", "")
    image_idea = fields.get("IMAGE IDEA", "").strip()

    if not title:
        raise RuntimeError(
            "Gemini did not return a valid video title."
        )

    if not description:
        description = (
            "Discover amazing facts in this YouTube Shorts video!"
        )

    tags = [
        tag.strip()
        for tag in tags_text.split(",")
        if tag.strip()
    ]

    if not tags:
        tags = ["facts", "science", "shorts", "education"]

    description += "\n\n#Shorts #Facts #Education"

    print("Video title:", title)
    print("Image idea:", image_idea)

    return title, description, tags, image_idea


# =========================================================
# STEP 3 — GENERATE ENGLISH VOICEOVER
# =========================================================

def create_voice(script):

    print("3. Generating English voiceover...")

    tts = gTTS(
        text=script,
        lang="en",
        slow=False
    )

    tts.save(AUDIO_FILE)

    print("Voiceover created:", AUDIO_FILE)

    return AUDIO_FILE


# =========================================================
# STEP 4 — GENERATE AI BACKGROUND IMAGE
# =========================================================

def generate_background_image(script, title, image_idea):

    print("4. Generating topic-specific AI image...")

    client = get_gemini_client()

    prompt = f"""
Create a beautiful, cinematic background image
for a YouTube Shorts video.

VIDEO TITLE:
{title}

VIDEO SCRIPT:
{script}

VISUAL CONCEPT:
{image_idea}

Requirements:
- Portrait 9:16 aspect ratio.
- The image must match the actual topic.
- Make the main subject large, clear and visually interesting.
- Professional cinematic lighting.
- Rich details and strong composition.
- Suitable for a general international audience.
- Leave some uncluttered space for subtitles.
- No text, letters, logos or watermarks.
- Generate an actual image, not a text description.
"""

    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio="9:16",
                image_size="1K"
            )
        )
    )

    for part in response.parts:

        if part.inline_data is not None:

            generated_image = part.as_image()

            # Save a real image in the current working directory.
            generated_image.save(BACKGROUND_IMAGE)

            # Validate that the output can be opened.
            with Image.open(BACKGROUND_IMAGE) as image:
                image.verify()

            print(
                "AI background created:",
                BACKGROUND_IMAGE
            )

            return BACKGROUND_IMAGE

    raise RuntimeError(
        "No image was returned by Gemini. "
        "Check IMAGE_MODEL, API access and quota."
    )


# =========================================================
# STEP 5 — CREATE VERTICAL SHORTS VIDEO
# =========================================================

def create_video(audio_file, script):

    print("5. Creating YouTube Shorts video...")

    if not os.path.isfile(BACKGROUND_IMAGE):
        raise FileNotFoundError(
            f"{BACKGROUND_IMAGE} not found. "
            "Generate the AI image before creating the video."
        )

    audio = None
    background = None
    text_clip = None
    video = None

    try:
        audio = AudioFileClip(audio_file)
        duration = audio.duration

        # Open the generated image and resize/crop to 9:16.
        with Image.open(BACKGROUND_IMAGE) as image:
            image = image.convert("RGB")
            image.save("background_video.jpg", quality=95)

        background = (
            ImageClip("background_video.jpg")
            .resize(height=1920)
            .set_duration(duration)
        )

        background = background.crop(
            width=1080,
            height=1920,
            x_center=background.w / 2,
            y_center=background.h / 2
        )

        # Prepare readable subtitles.
        wrapped_text = textwrap.fill(
            script,
            width=32
        )

        try:
            text_clip = (
                TextClip(
                    wrapped_text,
                    fontsize=55,
                    color="white",
                    bg_color="black",
                    size=(950, None),
                    method="caption",
                    align="center"
                )
                .set_position(("center", "center"))
                .set_duration(duration)
            )

            video = CompositeVideoClip(
                [background, text_clip],
                size=(1080, 1920)
            )

        except Exception as error:
            print("Subtitle creation failed:", error)
            print("Continuing without subtitles.")

            video = CompositeVideoClip(
                [background],
                size=(1080, 1920)
            )

        video = video.set_audio(audio)

        video.write_videofile(
            VIDEO_FILE,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=2
        )

        print("Video created:", VIDEO_FILE)

        return VIDEO_FILE

    finally:
        if video is not None:
            video.close()

        if text_clip is not None:
            text_clip.close()

        if background is not None:
            background.close()

        if audio is not None:
            audio.close()


# =========================================================
# STEP 6 — YOUTUBE AUTHENTICATION
# =========================================================

def get_youtube_service():

    print("6. Connecting to YouTube...")

    credentials = None

    # On GitHub Actions, supply token.json through a secret.
    token_json = os.environ.get("YOUTUBE_TOKEN_JSON")

    if token_json and not os.path.isfile(TOKEN_FILE):
        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(token_json)

    if os.path.isfile(TOKEN_FILE):
        credentials = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )

    if not credentials or not credentials.valid:

        if (
            credentials
            and credentials.expired
            and credentials.refresh_token
        ):
            print("Refreshing YouTube access token...")
            credentials.refresh(Request())

        else:
            # Interactive browser login is not suitable for
            # an unattended GitHub Actions runner.
            if os.environ.get("GITHUB_ACTIONS") == "true":
                raise RuntimeError(
                    "YouTube OAuth is not configured. "
                    "Create an authorized token.json with a refresh "
                    "token and save its complete JSON as the "
                    "YOUTUBE_TOKEN_JSON GitHub Actions secret."
                )

            if not os.path.isfile(CLIENT_SECRETS_FILE):
                raise FileNotFoundError(
                    f"{CLIENT_SECRETS_FILE} is missing."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE,
                SCOPES
            )

            credentials = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(credentials.to_json())

    return build(
        "youtube",
        "v3",
        credentials=credentials
    )


# =========================================================
# STEP 7 — UPLOAD VIDEO TO YOUTUBE
# =========================================================

def upload_to_youtube(video_file, title, description, tags):

    print("7. Uploading video to YouTube...")

    youtube = get_youtube_service()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": CATEGORY_ID,
            "defaultLanguage": "en"
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(
        video_file,
        mimetype="video/mp4",
        resumable=True
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
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
    print("VIDEO UPLOADED SUCCESSFULLY!")
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

    # 1. Generate the script for the chosen topic.
    script = generate_script(TOPIC)

    # 2. Generate a title, description, tags and visual concept.
    title, description, tags, image_idea = (
        generate_video_metadata(script)
    )

    # 3. Generate the English voiceover.
    audio_file = create_voice(script)

    # 4. Generate a matching AI background image.
    generate_background_image(
        script,
        title,
        image_idea
    )

    # 5. Create the vertical video.
    video_file = create_video(
        audio_file,
        script
    )

    # 6. Upload using the generated metadata.
    upload_to_youtube(
        video_file,
        title,
        description,
        tags
    )

    print()
    print("====================================")
    print("          PIPELINE COMPLETE")
    print("====================================")


if __name__ == "__main__":
    main()
