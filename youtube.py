import os
from google import genai
from gtts import gTTS
from moviepy.editor import AudioFileClip, ImageClip, TextClip, CompositeVideoClip

# ---------------------------------------------------------
# CONFIGURATION & SETTINGS
# ---------------------------------------------------------
# API Açarını sistem mühit dəyişənlərindən oxuyur
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

TOPIC = "Kosmos haqqında 3 maraqlı fakt"
BACKGROUND_IMAGE_PATH = "background.jpg"
OUTPUT_VIDEO_PATH = "youtube_short.mp4"

# ---------------------------------------------------------
# STEP 1: GENERATE SCRIPT (Gemini API)
# ---------------------------------------------------------
def generate_script(topic: str) -> str:
    print("1. Ssenari hazırlanır (Gemini API)...")
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY mühit dəyişəni tapılmadı!")
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = (
        f"YouTube Short üçün '{topic}' mövzusunda maksimum 30-40 sözdən ibarət, "
        f"diqqətçəkici və axıcı Azərbaycan dilində ssenari yaz. Ancaq oxunacaq mətni qaytar."
    )
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    
    script = response.text.strip()
    print(f"Hazırlanmış ssenari:\n{script}\n")
    return script

# ---------------------------------------------------------
# STEP 2: GENERATE VOICE (gTTS)
# ---------------------------------------------------------
def text_to_speech(text: str, output_audio="voiceover.mp3") -> str:
    print("2. Səs faylı yaradılır (Text-to-Speech)...")
    tts = gTTS(text=text, lang='az', slow=False)
    tts.save(output_audio)
    return output_audio

# ---------------------------------------------------------
# STEP 3: CREATE VIDEO (MoviePy)
# ---------------------------------------------------------
def create_video(audio_path: str, script_text: str, bg_image_path: str, output_path: str):
    print("3. Video montaj olunur (MoviePy)...")
    
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    bg_clip = (
        ImageClip(bg_image_path)
        .set_duration(duration)
        .resize(newsize=(1080, 1920))
    )

    # Subtitr / Mətn tərtibatı
    try:
        txt_clip = (
            TextClip(
                script_text,
                fontsize=40,
                color='white',
                bg_color='black',
                size=(900, None),
                method='caption'
            )
            .set_position('center')
            .set_duration(duration)
        )
        video = CompositeVideoClip([bg_clip, txt_clip]).set_audio(audio_clip)
    except Exception as e:
        print(f"Xəbərdarlıq: TextClip xətası (ImageMagick çatışmır): {e}")
        print("Video yalnız arxa fon və səs ilə yaradılır...")
        video = bg_clip.set_audio(audio_clip)

    video.write_videofile(
        output_path,
        fps=30,
        codec='libx264',
        audio_codec='aac'
    )
    
    audio_clip.close()
    video.close()
    print(f"Video uğurla yaradıldı: {output_path}")

# ---------------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------------
if __name__ == "__main__":
    script = generate_script(TOPIC)
    audio_file = text_to_speech(script)
    
    if os.path.exists(BACKGROUND_IMAGE_PATH):
        create_video(audio_file, script, BACKGROUND_IMAGE_PATH, OUTPUT_VIDEO_PATH)
    else:
        print(f"Xəta: '{BACKGROUND_IMAGE_PATH}' faylı tapılmadı! Qovluğa şəkil daxil edin.")