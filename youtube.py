import os
import re
import textwrap

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
# 1. CONFIGURATION
# =========================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

TEXT_MODEL = os.environ.get(
    "GEMINI_TEXT_MODEL",
    "gemini-2.5-flash",
)

IMAGE_MODEL = os.environ.get(
    "GEMINI_IMAGE_MODEL",
    "gemini-2.5-flash-image",
)

TOPIC = os.environ.get(
    "VIDEO_TOPIC",
    "3 Amazing Facts About Space",
)

BACKGROUND_IMAGE = "background.png"
AUDIO_FILE = "voiceover.mp3"
VIDEO_FILE = "youtube_short.mp4"
TEMP_IMAGE = "background_video.jpg"

CLIENT_SECRETS_FILE = "client_secrets.json"
TOKEN_FILE = "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload"
]

CATEGORY_ID = "28"
PRIVACY_STATUS = os.environ.get(
    "YOUTUBE_PRIVACY_STATUS",
    "public",
)


# =========================================================
# 2. GEMINI CLIENT
# =========================================================

def get_gemini_client():
    """Create and return the Gemini API client."""

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is missing. "
            "Add it in GitHub Settings > Secrets and variables > Actions."
        )

    return genai.Client(api_key=api_key)


# =========================================================
# 3. GENERATE ENGLISH SCRIPT
# =========================================================

def generate_script(topic):
    """Generate a short English YouTube Shorts script."""

    print("1. Generating English script...")

    client = get_gemini_client()

    prompt = f"""
Create an engaging YouTube Shorts script in English.

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
        contents=prompt,
    )

    script = (response.text or "").strip()

    if not script:
        raise RuntimeError(
            "Gemini returned an empty script. "
            "Check the model name, API key and quota."
        )

    print("\n========== SCRIPT ==========")
    print(script)
    print("============================\n")

    return script


# =========================================================
# 4. GENERATE TITLE, DESCRIPTION, TAGS AND IMAGE IDEA
# =========================================================

def generate_video_metadata(script):
    """Generate YouTube metadata and a matching image concept."""

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
        contents=prompt,
    )

    result = (response.text or "").strip()

    if not result:
        raise RuntimeError(
            "Gemini failed to generate video metadata."
        )

    fields = {}

    for line in result.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip().upper()] = value.strip()

    title = fields.get("TITLE", "").strip()
    description = fields.get("DESCRIPTION", "").strip()
    tags_text = fields.get("TAGS", "").strip()
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
        tags = [
            "facts",
            "science",
            "education",
            "shorts",
        ]

    # Keep YouTube tags within a reasonable count.
    tags = tags[:15]

    description += "\n\n#Shorts #Facts #Education"

    print("Video title:", title)
    print("Image idea:", image_idea)

    return title, description, tags, image_idea


# =========================================================
# 5. GENERATE ENGLISH VOICEOVER
# =========================================================

def create_voice(script):
    """Convert the script to English speech."""

    print("3. Generating English voiceover...")

    tts = gTTS(
        text=script,
        lang="en",
        slow=False,
    )

    tts.save(AUDIO_FILE)

    if not os.path.isfile(AUDIO_FILE):
        raise RuntimeError(
            "The voiceover audio file was not created."
        )

    print("Voiceover created:", AUDIO_FILE)

    return AUDIO_FILE


# =========================================================
# 6. GENERATE AI BACKGROUND IMAGE
# =========================================================

def generate_background_image(script, title, image_idea):
    """Generate an image that matches the video's topic."""

    print("4. Generating topic-specific AI image...")

    client = get_gemini_client()

    prompt = f"""
Create an actual cinematic image for a YouTube Shorts video.

VIDEO TITLE:
{title}

VIDEO SCRIPT:
{script}

VISUAL CONCEPT:
{image_idea}

Requirements:
- Portrait 9:16 composition.
- The image must match the topic and script.
- Make the main subject large, clear and interesting.
- Professional cinematic lighting.
- Detailed, visually appealing composition.
- Suitable for a general international audience.
- Leave some uncluttered space for subtitles.
- No text, letters, logos or watermarks.
- Return a generated image, not a text description.
"""

    response = client.models.generate_content(
        model=IMAGE_MODEL,
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

        if part.inline_data is not None:
            generated_image = part.as_image()
            generated_image.save(BACKGROUND_IMAGE)

            # Confirm that the image is valid.
            with Image.open(BACKGROUND_IMAGE) as image:
                image.verify()

            print(
                "AI background created:",
                BACKGROUND_IMAGE,
            )

            return BACKGROUND_IMAGE

    raise RuntimeError(
        "Gemini did not return an image. "
        "Check the IMAGE_MODEL name, API access and quota."
    )


# =========================================================
# 7. CREATE VERTICAL SHORTS VIDEO
# =========================================================

def create_video(audio_file, script):
    """Combine the background image, voiceover and subtitles."""

    print("5. Creating YouTube Shorts video...")

    if not os.path.isfile(BACKGROUND_IMAGE):
        raise FileNotFoundError(
            f"{BACKGROUND_IMAGE} was not found."
        )

    audio = None
    background = None
    text_clip = None
    video = None

    try:
        audio = AudioFileClip(audio_file)
        duration = audio.duration

        if not duration or duration <= 0:
            raise RuntimeError(
                "The voiceover has an invalid duration."
            )

        # Convert the generated image to a video-friendly format.
        with Image.open(BACKGROUND_IMAGE) as image:
            image.convert("RGB").save(
                TEMP_IMAGE,
                quality=95,
            )

        # MoviePy 1.x API.
        background = (
            ImageClip(TEMP_IMAGE)
            .resize(height=1920)
            .set_duration(duration)
        )

        # Center-crop to 1080 x 1920.
        background = background.crop(
            width=1080,
            height=1920,
            x_center=background.w / 2,
            y_center=background.h / 2,
        )

        wrapped_text = textwrap.fill(
            script,
            width=32,
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
            print("Subtitle creation failed:", error)
            print("Continuing without subtitles.")

            video = CompositeVideoClip(
                [background],
                size=(1080, 1920),
            )

        video = video.set_audio(audio)

        video.write_videofile(
            VIDEO_FILE,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=2,
        )

        print("Video created:", VIDEO_FILE)

        return VIDEO_FILE

    finally:
        # Close MoviePy resources.
        if video is not None:
            video.close()

        if text_clip is not None:
            text_clip.close()

        if background is not None:
            background.close()

        if audio is not None:
            audio.close()


# =========================================================
# 8. YOUTUBE AUTHENTICATION
# =========================================================

def get_youtube_service():
    """Authenticate with YouTube using the saved OAuth token."""

    print("6. Connecting to YouTube...")

    credentials = None

    # Support either secret name.
    token_json = (
        os.environ.get("YOUTUBE_TOKEN_JSON")
        or os.environ.get("TOKEN_JSON")
    )

    # On GitHub Actions, write the secret to token.json.
    if token_json:
        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(token_json)

    if os.path.isfile(TOKEN_FILE):
        credentials = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES,
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
            # GitHub Actions cannot complete an interactive login.
            if os.environ.get("GITHUB_ACTIONS") == "true":
                raise RuntimeError(
                    "YouTube OAuth is not configured correctly. "
                    "Create token.json locally with a refresh token "
                    "and save its complete JSON as the "
                    "YOUTUBE_TOKEN_JSON GitHub Actions secret."
                )

            if not os.path.isfile(CLIENT_SECRETS_FILE):
                raise FileNotFoundError(
                    f"{CLIENT_SECRETS_FILE} is missing."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE,
                SCOPES,
            )

            credentials = flow.run_local_server(
                port=0,
                access_type="offline",
                prompt="consent",
            )

        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(credentials.to_json())

    return build(
        "youtube",
        "v3",
        credentials=credentials,
    )


# =========================================================
# 9. UPLOAD VIDEO TO YOUTUBE
# =========================================================

def upload_to_youtube(video_file, title, description, tags):
    """Upload the generated video to the YouTube channel."""

    print("7. Uploading video to YouTube...")

    youtube = get_youtube_service()

    body = {
        "snippet": {
            "title": title,
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
    video_url = (
        f"https://www.youtube.com/watch?v={video_id}"
    )

    print("\n================================")
    print("VIDEO UPLOADED SUCCESSFULLY!")
    print("Title:", title)
    print("Video ID:", video_id)
    print("URL:", video_url)
    print("================================")

    return video_id


# =========================================================
# 10. MAIN PIPELINE
# =========================================================

def main():

    print()
    print("====================================")
    print("     ENGLISH YOUTUBE AUTOMATION")
    print("====================================")
    print()

    # Step 1: Generate script.
    script = generate_script(TOPIC)

    # Step 2: Generate metadata and visual concept.
    title, description, tags, image_idea = (
        generate_video_metadata(script)
    )

    # Step 3: Generate voiceover.
    audio_file = create_voice(script)

    # Step 4: Generate the AI background.
    generate_background_image(
        script,
        title,
        image_idea,
    )

    # Step 5: Create the vertical video.
    video_file = create_video(
        audio_file,
        script,
    )

    # Step 6: Upload to YouTube.
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
    main()
