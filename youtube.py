import os
import textwrap

from google import genai
from gtts import gTTS

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

TOPIC = "3 Amazing Facts About Space"

BACKGROUND_IMAGE = "background.jpg"
AUDIO_FILE = "voiceover.mp3"
VIDEO_FILE = "youtube_short.mp4"

CLIENT_SECRETS_FILE = "client_secrets.json"
TOKEN_FILE = "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload"
]

# YouTube information
VIDEO_TITLE = "3 Amazing Facts About Space 🚀"

VIDEO_DESCRIPTION = """
Did you know these amazing facts about space?

Discover 3 incredible facts about the universe
in this short video!

Subscribe for more amazing facts.

#space #science #facts #universe #astronomy #shorts
"""

VIDEO_TAGS = [
    "space",
    "space facts",
    "amazing facts",
    "science",
    "universe",
    "astronomy",
    "interesting facts",
    "did you know",
    "shorts"
]

CATEGORY_ID = "28"

# public / private / unlisted
PRIVACY_STATUS = "public"


# =========================================================
# STEP 1 — GENERATE ENGLISH SCRIPT
# =========================================================

def generate_script(topic):

    print("1. Generating English script with Gemini...")

    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY was not found!"
        )

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    prompt = f"""
Create a YouTube Shorts script in English.

Topic:
{topic}

Requirements:

- 30-50 words
- Start with a very strong hook
- Make it exciting and easy to understand
- Use natural spoken English
- Suitable for an international audience
- No emojis
- Do not write a title
- Do not say "Hello"
- Return ONLY the text that should be spoken
"""

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt
    )

    script = response.text.strip()

    print("\n========== SCRIPT ==========")
    print(script)
    print("============================\n")

    return script


# =========================================================
# STEP 2 — ENGLISH TEXT TO SPEECH
# =========================================================

def create_voice(script):

    print("2. Generating English voiceover...")

    tts = gTTS(
        text=script,
        lang="en",
        slow=False
    )

    tts.save(AUDIO_FILE)

    print(
        f"Voiceover created: {AUDIO_FILE}"
    )

    return AUDIO_FILE


# =========================================================
# STEP 3 — CREATE VERTICAL VIDEO
# =========================================================

def create_video(audio_file, script):

    print("3. Creating YouTube Shorts video...")

    if not os.path.exists(BACKGROUND_IMAGE):

        raise FileNotFoundError(
            f"{BACKGROUND_IMAGE} was not found!"
        )

    audio = AudioFileClip(
        audio_file
    )

    duration = audio.duration

    # -----------------------------------------------------
    # Background image
    # -----------------------------------------------------

    background = (
        ImageClip(BACKGROUND_IMAGE)
        .set_duration(duration)
        .resize(height=1920)
    )

    # Crop to 1080x1920
    background = background.crop(
        width=1080,
        height=1920,
        x_center=background.w / 2,
        y_center=background.h / 2
    )

    # -----------------------------------------------------
    # Subtitles
    # -----------------------------------------------------

    wrapped_text = textwrap.fill(
        script,
        width=35
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
            [
                background,
                text_clip
            ]
        )

    except Exception as error:

        print(
            "TextClip error:"
        )

        print(error)

        print(
            "Creating video without subtitles..."
        )

        video = background

    # Add voice
    video = video.set_audio(audio)

    # -----------------------------------------------------
    # Export MP4
    # -----------------------------------------------------

    video.write_videofile(
        VIDEO_FILE,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="medium"
    )

    audio.close()
    video.close()

    print(
        f"Video created successfully: {VIDEO_FILE}"
    )

    return VIDEO_FILE


# =========================================================
# STEP 4 — YOUTUBE AUTHENTICATION
# =========================================================

def get_youtube_service():

    print("4. Connecting to YouTube...")

    credentials = None

    if os.path.exists(TOKEN_FILE):

        credentials = (
            Credentials.from_authorized_user_file(
                TOKEN_FILE,
                SCOPES
            )
        )

    if not credentials or not credentials.valid:

        if (
            credentials
            and credentials.expired
            and credentials.refresh_token
        ):

            print(
                "Refreshing YouTube token..."
            )

            credentials.refresh(
                Request()
            )

        else:

            print(
                "Starting Google OAuth..."
            )

            flow = (
                InstalledAppFlow
                .from_client_secrets_file(
                    CLIENT_SECRETS_FILE,
                    SCOPES
                )
            )

            credentials = (
                flow.run_local_server(
                    port=0
                )
            )

        with open(
            TOKEN_FILE,
            "w"
        ) as token:

            token.write(
                credentials.to_json()
            )

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials
    )

    return youtube


# =========================================================
# STEP 5 — UPLOAD VIDEO TO YOUTUBE
# =========================================================

def upload_to_youtube(video_file):

    print("5. Uploading video to YouTube...")

    youtube = get_youtube_service()

    body = {
        "snippet": {
            "title": VIDEO_TITLE,
            "description": VIDEO_DESCRIPTION,
            "tags": VIDEO_TAGS,
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

            progress = int(
                status.progress() * 100
            )

            print(
                f"Upload progress: {progress}%"
            )

    video_id = response["id"]

    video_url = (
        f"https://www.youtube.com/watch?v={video_id}"
    )

    print("\n================================")
    print("VIDEO UPLOADED SUCCESSFULLY!")
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

    # 1. Generate English script
    script = generate_script(
        TOPIC
    )

    # 2. Generate English voice
    audio_file = create_voice(
        script
    )

    # 3. Create vertical video
    video_file = create_video(
        audio_file,
        script
    )

    # 4. Upload to YouTube
    upload_to_youtube(
        video_file
    )

    print()
    print("====================================")
    print("          PIPELINE COMPLETE")
    print("====================================")


# =========================================================

if __name__ == "__main__":
    main()
