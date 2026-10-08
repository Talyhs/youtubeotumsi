import os
from google import genai
from gtts import gTTS
from moviepy.editor import AudioFileClip, ImageClip, TextClip, CompositeVideoClip
from tenacity import retry, stop_after_attempt, wait_fixed

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

TOPIC = "Kosmos haqqında 3 maraqlı fakt"
BACKGROUND_IMAGE_PATH = "background.jpg"
OUTPUT_VIDEO_PATH = "youtube_short.mp4"


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def generate_script(topic: str) -> str:
    print("1. Ssenari hazırlanır (Gemini API)...")

    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY mühit dəyişəni tapılmadı!")

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = (
        f"YouTube Short üçün '{topic}' mövzusunda "
        f"maksimum 30-40 sözdən ibarət, diqqətçəkici və "
        f"axıcı Azərbaycan dilində ssenari yaz. "
        f"Ancaq oxunacaq mətni qaytar."
    )

    response = client.models.generate_content(
        model="BURAYA_DUZGUN_GEMINI_MODELI",
        contents=prompt,
    )

    script = response.text.strip()

    print(f"Hazırlanmış ssenari:\n{script}\n")

    return script
