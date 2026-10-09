
import json
import os
import re
import subprocess
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlparse

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
SUBTITLE_FILE = WORK / "subtitles.ass"
SCENE_FILE = WORK / "scenes.txt"
TOKEN_FILE = BASE / "token.json"

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
PEXELS_KEY = os.getenv("PEXELS_API_KEY", "").strip()
PIXABAY_KEY = os.getenv("PIXABAY_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_TEXT_MODEL", "").strip() or "gemini-3.8-flash"
TOPIC = os.getenv("VIDEO_TOPIC", "").strip() or "10 maraqlı fakt"
VOICE = os.getenv("EDGE_TTS_VOICE", "").strip() or "az-AZ-BabekNeural"
PRIVACY = os.getenv("YOUTUBE_PRIVACY_STATUS", "public").strip().lower()

if PRIVACY not in {"public", "private", "unlisted"}:
    raise RuntimeError(
        "YOUTUBE_PRIVACY_STATUS must be public, private or unlisted."
    )

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CATEGORY = "27"
HEADERS = {"User-Agent": "TalyhsYouTubeAutomation/1.0"}
TIMEOUT = 60

# Daily topic rotation in Azerbaijan time; topics cycle only after 30 days.
DAILY_TOPICS = [
    ("Kosmos və planetlər haqqında", ["space planets galaxy", "astronaut outer space", "solar system stars"]),
    ("Okean və dənizlər haqqında", ["deep ocean sea life", "underwater coral reef", "ocean waves marine animals"]),
    ("İnsan bədəni haqqında", ["human body science", "human brain medical animation", "heart anatomy educational"]),
    ("Heyvanlar aləmi haqqında", ["wild animals nature", "animal behavior wildlife", "birds mammals nature"]),
    ("Dünya və təbiət möcüzələri haqqında", ["natural wonders landscape", "waterfalls mountains nature", "volcano forest nature"]),
    ("Tarixdən maraqlı hadisələr haqqında", ["ancient civilization ruins", "historical artifacts museum", "ancient architecture"]),
    ("Elm və fizika haqqında", ["science laboratory experiment", "physics experiment education", "scientist laboratory"]),
    ("Texnologiya və süni intellekt haqqında", ["artificial intelligence technology", "robotics computer technology", "futuristic technology"]),
    ("Qədim sivilizasiyalar haqqında", ["ancient civilization pyramids", "archaeology excavation", "ancient ruins"]),
    ("Qida və gündəlik həyat haqqında", ["food science kitchen", "fresh food market", "cooking ingredients closeup"]),
    ("Yuxu və beyin haqqında", ["sleeping person night", "brain neuroscience animation", "dream sleep science"]),
    ("Dünyanın ən qəribə yerləri haqqında", ["unusual places on earth", "strange landscapes travel", "remote island aerial"]),
    ("İxtiralar və kəşflər haqqında", ["scientific inventions workshop", "inventions museum", "engineering innovation"]),
    ("Riyaziyyat və rəqəmlər haqqında", ["mathematics numbers classroom", "geometry equations writing", "numbers data visualization"]),
    ("Bitkilər və meşələr haqqında", ["forest plants closeup", "tropical rainforest wildlife", "flowers growing time lapse"]),
    ("Hava və iqlim haqqında", ["weather clouds storm", "lightning thunderstorm", "climate nature landscape"]),
    ("İnsan psixologiyası haqqında", ["people thinking psychology", "human behavior crowd", "person reflecting window"]),
    ("Gündəlik əşyaların sirri haqqında", ["everyday objects close up", "household items macro", "manufacturing everyday products"]),
    ("Dünya rekordları haqqında", ["world record sports action", "extreme nature records", "largest structures aerial"]),
    ("Məşhur alimlər və kəşflər haqqında", ["scientist working laboratory", "science history books", "research microscope laboratory"]),
    ("Günəş və ulduzlar haqqında", ["sun solar flare space", "stars night sky", "telescope astronomy observatory"]),
    ("Quşlar haqqında", ["birds flying wildlife", "eagle in flight nature", "colorful birds close up"]),
    ("Həşəratlar haqqında", ["insects macro photography", "bees pollinating flowers", "butterfly macro nature"]),
    ("İnsan duyğuları haqqında", ["human facial expressions", "people emotions portrait", "person smiling thoughtful"]),
    ("Nəqliyyat və maşınlar haqqında", ["modern transport cars trains", "airplane flying sky", "electric vehicle technology"]),
    ("Yer kürəsinin geologiyası haqqında", ["rock formations geology", "volcano lava eruption", "mountain geology landscape"]),
    ("Dünya mədəniyyətləri haqqında", ["world cultures traditional art", "traditional architecture travel", "cultural festival people"]),
    ("Dəniz canlıları haqqında", ["marine animals underwater", "dolphins swimming ocean", "sea turtles coral reef"]),
    ("İşıq və optika haqqında", ["light prism rainbow experiment", "optics science experiment", "laser light laboratory"]),
    ("Gündəlik elmi faktlar haqqında", ["everyday science experiment", "science facts demonstration", "macro objects scientific"]),
]

def get_daily_topic():
    """Pick a repeatable topic by day in Azerbaijan time."""
    today = datetime.now(ZoneInfo("Asia/Baku")).date()
    index = (today.timetuple().tm_yday - 1) % len(DAILY_TOPICS)
    topic, queries = DAILY_TOPICS[index]
    print(f"Daily Azerbaijani topic ({today.isoformat()}): {topic}")
    return topic, queries


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

    fallback_models = [
        item.strip()
        for item in os.getenv(
            "GEMINI_FALLBACK_MODELS",
            "gemini-3.7-flash,gemini-3.5-flash-lite",
        ).split(",")
        if item.strip()
    ]
    models_to_try = list(dict.fromkeys([MODEL] + fallback_models))

    for model_name in models_to_try:
        print(f"Generating text with Gemini model: {model_name}")
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                result = (response.text or "").strip()
                if not result:
                    raise RuntimeError(
                        f"Gemini model {model_name} returned an empty response."
                    )
                return result
            except Exception as exc:
                last_error = exc
                message = str(exc).lower()
                retryable = any(
                    item in message
                    for item in (
                        "429", "500", "502", "503", "504",
                        "resource exhausted", "temporarily unavailable",
                        "high demand", "unavailable",
                    )
                )
                model_unavailable = any(
                    item in message
                    for item in (
                        "404", "not found", "no longer available",
                        "unsupported model", "model is not supported",
                    )
                )

                if model_unavailable:
                    print(
                        f"Gemini model {model_name} is unavailable; "
                        "trying the next configured model."
                    )
                    break

                if retryable:
                    if attempt < 2:
                        delay = (3, 8, 15)[attempt]
                        print(
                            f"Gemini {model_name} temporarily failed "
                            f"(attempt {attempt + 1}/3): {exc}. "
                            f"Retrying in {delay}s."
                        )
                        time.sleep(delay)
                        continue
                    print(
                        f"Gemini {model_name} remained unavailable after "
                        "3 attempts; trying the next model."
                    )
                    break

                raise

    raise RuntimeError(
        "All configured Gemini models failed. Last error: "
        + str(last_error)
    ) from last_error

def generate_script(topic):
    print("1. Azərbaycan dilində 10 maraqlı fakt hazırlanır...")

    prompt = f"""
Azərbaycan dilində YouTube videosu üçün təbii səslənən ssenari yaz.
Mövzu: {topic}

Tələblər:
- Dəqiq 10 fərqli və mümkün qədər etibarlı, həqiqətə uyğun fakt təqdim et.
- Mətn 390-430 Azərbaycan sözü olsun; videonun hədəf müddəti 3 dəqiqə 13 saniyədir.
- Təbii danışıq dili, qısa cümlələr və səsli oxunuş üçün rahat ritm istifadə et.
- İlk 5 saniyədə güclü maraq oyadan sual və ya təəccüblü ziddiyyət yarat; cavabı dərhal açma.
- Giriş 1-2 cümlə olsun, uzadılmış salamlaşma yazma.
- Hər faktı "1-ci fakt", "2-ci fakt" formasında başlat; hər faktın ilk cümləsi maraq oyatsın.
- Faktlar arasında qısa, təbii keçidlər və açıq suallar istifadə et ki, tamaşaçı növbəti faktı gözləsin.
- 3-cü və 7-ci faktlardan əvvəl marağı artıran keçid ver, cavabı həmin faktın içində aç.
- Faktlar qısa, konkret, bir-birindən fərqli olsun. Uydurma rəqəmlər, saxta sitatlar və sübut olunmamış iddialar yazma.
- Təxminən hər 20-30 saniyədə yeni maraq elementi olsun; ritm sürətli qalsın.
- Sonda ən maraqlı faktı xatırladan qısa sual və təbii abunə çağırışı ver.
- Başlıq, markdown, URL və səhnə göstərişləri yazma; yalnız səsləndiriləcək mətni qaytar.
"""
    script = generate_text(prompt)
    word_count = len(re.findall(r"\b[\wƏəIıİiÖöÜüĞğŞşÇç]+\b", script, flags=re.UNICODE))
    if not 390 <= word_count <= 430:
        print(f"Generated script has {word_count} words; requesting one correction.")
        correction_prompt = (
            "Aşağıdakı Azərbaycan dilində ssenarini məzmununu və 10 faktını qoruyaraq "
            "390-430 söz aralığına düzəlt. İlk 5 saniyənin girişini və son çağırışı saxla. "
            "Yalnız ssenarini qaytar, əlavə izah yazma.\n\n" + script
        )
        script = generate_text(correction_prompt)
    word_count = len(re.findall(r"\b[\wƏəIıİiÖöÜüĞğŞşÇç]+\b", script, flags=re.UNICODE))
    if not 390 <= word_count <= 430:
        raise RuntimeError(
            f"Gemini ssenarisi {word_count} sözdür; tələb olunan aralıq 390-430 sözdür. "
            "GEMINI_FALLBACK_MODELS ayarını yoxlayın və workflow-u yenidən başladın."
        )
    print(f"Script word count: {word_count}")
    print(script)
    return script


def generate_metadata(script):
    """Build SEO title, description, tags and include the full spoken script."""
    print("2. Azərbaycan dilində SEO başlığı, açıqlama və etiketlər hazırlanır...")

    topic = TOPIC.strip() or "maraqlı faktlar"
    title = f"10 Maraqlı Fakt: {topic}"[:100].rstrip(" -,:;|")
    topic_words = re.findall(r"[A-Za-zƏəIıİiÖöÜüĞğŞşÇç]+", topic.lower())
    topic_words = [word for word in topic_words if word not in {
        "haqqında", "barədə", "və", "olan", "üçün"
    }]
    keywords = list(dict.fromkeys(topic_words + [
        "10 maraqlı fakt", "maraqlı məlumatlar", "Azərbaycan dilində",
        "elm", "öyrən", "faktlar"
    ]))
    tags = keywords[:15]

    hashtags = ["#MaraqlıFaktlar", "#Azərbaycan", "#Elm"]
    if topic_words:
        topic_hashtag = "#" + "".join(
            word[:1].upper() + word[1:] for word in topic_words[:2]
        )
        if topic_hashtag not in hashtags:
            hashtags.insert(0, topic_hashtag)
    hashtags = hashtags[:4]

    description = (
        f"{topic.capitalize()} mövzusunda 10 maraqlı fakt! "
        f"Bu videoda {', '.join(topic_words[:4]) if topic_words else 'maraqlı mövzular'} "
        "haqqında qısa, maarifləndirici məlumatlar öyrənəcəksiniz. "
        "Yeni faktlar və biliklər üçün videonu sonadək izləyin, fikrinizi şərhdə yazın "
        "və kanala abunə olun.\n\n"
        "VİDEODA SƏSLƏNƏN MƏTN:\n"
        + script.strip()
        + "\n\n"
        + " ".join(hashtags)
    )
    print("SEO metadata and full narration text generated locally.")
    return title, description[:4900], tags, []

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
    print("4. Edge TTS ilə Azərbaycan dilində səs və diqqətçəkən subtitrlər hazırlanır...")

    import asyncio
    import edge_tts

    if not script.strip():
        raise RuntimeError("Cannot synthesize an empty script.")

    async def synthesize():
        communicate = edge_tts.Communicate(script, VOICE, rate="+0%")
        await communicate.save(str(AUDIO_FILE))

    try:
        asyncio.run(synthesize())
    except Exception as exc:
        raise RuntimeError(
            f"Edge TTS səs yaradılması uğursuz oldu ({VOICE}): {exc}"
        ) from exc

    if not AUDIO_FILE.exists() or AUDIO_FILE.stat().st_size == 0:
        raise RuntimeError("Edge TTS did not create an audio file.")

    # Aim for 3:13. atempo adjusts playback speed without changing pitch.
    target_duration = float(os.getenv("TARGET_VIDEO_SECONDS", "193"))
    original_duration = get_audio_duration()
    tempo = original_duration / target_duration
    if not 0.80 <= tempo <= 1.25:
        raise RuntimeError(
            f"Səsləndirmə müddəti ({original_duration:.1f}s) 3:13 hədəfindən "
            "çox fərqlənir. Ssenarini təxminən 390-430 söz saxlayın."
        )
    adjusted_audio = WORK / "voiceover_adjusted.mp3"
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(AUDIO_FILE),
        "-filter:a", f"atempo={tempo:.6f}",
        "-t", f"{target_duration:.3f}",
        "-codec:a", "libmp3lame", "-q:a", "3",
        str(adjusted_audio),
    ])
    adjusted_audio.replace(AUDIO_FILE)
    audio_duration = get_audio_duration()
    print(f"Səsin hədəf müddəti: {audio_duration:.1f} saniyə.")

    def ass_stamp(seconds):
        cs = max(0, int(seconds * 100))
        hours, cs = divmod(cs, 360000)
        minutes, cs = divmod(cs, 6000)
        secs, cs = divmod(cs, 100)
        return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"

    # Word-level timestamps are estimated proportionally because this workflow
    # does not request speech timing data from Edge TTS.
    words = re.findall(r"\S+", script)
    if not words:
        raise RuntimeError("The generated script contains no words.")

    weights = [
        max(1, len(word))
        + (0.65 if word.endswith((".", "!", "?")) else
           0.25 if word.endswith((",", ";", ":")) else 0)
        for word in words
    ]
    total_weight = sum(weights)
    boundaries = []
    cursor = 0.0
    for word, weight in zip(words, weights):
        word_duration = audio_duration * weight / total_weight
        boundaries.append({"start": cursor, "duration": word_duration, "text": word})
        cursor += word_duration

    # Short captions (3-5 words) are easier to read on mobile screens.
    groups = []
    current = []
    for word in boundaries:
        if current and (
            len(current) >= 5
            or word["start"] - (current[-1]["start"] + current[-1]["duration"]) > 0.55
        ):
            groups.append(current)
            current = []
        current.append(word)
    if current:
        groups.append(current)

    ass_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,DejaVu Sans,54,&H00FFFFFF,&H0000FFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,3,4,1,2,100,100,95,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for group in groups:
        start_time = group[0]["start"]
        end_time = group[-1]["start"] + group[-1]["duration"]
        tokens = [item["text"] for item in group]
        focus_index = max(
            range(len(tokens)),
            key=lambda i: len(re.sub(r"[^A-Za-zƏəIıİiÖöÜüĞğŞşÇç]", "", tokens[i]))
        )
        caption_tokens = []
        for i, token in enumerate(tokens):
            safe_token = token.replace("{", "(").replace("}", ")")
            if i == focus_index:
                caption_tokens.append(r"{\c&H0000FFFF&}" + safe_token + r"{\c&H00FFFFFF&}")
            else:
                caption_tokens.append(safe_token)
        caption = " ".join(caption_tokens)
        ass_lines.append(
            f"Dialogue: 0,{ass_stamp(start_time)},{ass_stamp(max(start_time + 0.25, end_time))},"
            f"Default,,0,0,0,,{caption}"
        )

    SUBTITLE_FILE.write_text("\n".join(ass_lines) + "\n", encoding="utf-8")
    print("Qalın, kontrastlı ASS subtitrləri və sarı vurğulu açar sözlər hazırdır.")
    return audio_duration

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

    filter_arg = f"subtitles='{subtitle_path}'"

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
            "defaultLanguage": "az",
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
    global TOPIC
    TOPIC, stock_queries = get_daily_topic()
    print("Topic:", TOPIC)
    print("Gemini model:", MODEL)
    print("TTS voice:", VOICE)

    check_configuration()
    script = generate_script(TOPIC)
    title, description, tags, metadata_queries = generate_metadata(script)
    queries = stock_queries or metadata_queries
    clips = collect_clips(queries, wanted=5)
    duration = create_voice_and_subtitles(script)
    make_video(clips, duration)
    upload_video(title, description, tags, clips)

    print("Final MP4:", VIDEO_FILE)
    print("Subtitles:", SUBTITLE_FILE)


if __name__ == "__main__":
    main()
