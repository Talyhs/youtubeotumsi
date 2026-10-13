
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
LANGUAGE = os.getenv("VIDEO_LANGUAGE", "az").strip().lower()
VOICE_GENDER = os.getenv("VOICE_GENDER", "auto").strip().lower()
VOICE_MAP = {"az": {"auto": "az-AZ-BabekNeural", "male": "az-AZ-BabekNeural", "female": "az-AZ-BanuNeural"}, "en": {"auto": "en-US-GuyNeural", "male": "en-US-GuyNeural", "female": "en-US-JennyNeural"}, "tr": {"auto": "tr-TR-AhmetNeural", "male": "tr-TR-AhmetNeural", "female": "tr-TR-EmelNeural"}}
VOICE = os.getenv("EDGE_TTS_VOICE", "").strip() or VOICE_MAP.get(LANGUAGE, VOICE_MAP["az"]).get(VOICE_GENDER, VOICE_MAP.get(LANGUAGE, VOICE_MAP["az"])["auto"])
VIDEO_FORMAT = os.getenv("VIDEO_FORMAT", "horizontal").strip().lower()
ADD_SUBTITLES = os.getenv("ADD_SUBTITLES", "true").strip().lower() == "true"
CREATE_THUMBNAIL = os.getenv("CREATE_THUMBNAIL", "true").strip().lower() == "true"
PUBLISH_MODE = os.getenv("PUBLISH_MODE", "upload").strip().lower()
STOCK_SOURCES = {item.strip().lower() for item in os.getenv("STOCK_SOURCES", "Pixabay,Pexels").split(",") if item.strip()}
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

    script_override = os.getenv("SCRIPT_OVERRIDE_FILE", "").strip()
    local_script_available = bool(script_override and Path(script_override).is_file())
    if not GEMINI_KEY and not local_script_available:
        missing.append("GEMINI_API_KEY (or a valid SCRIPT_OVERRIDE_FILE for local Ollama mode)")

    if PUBLISH_MODE == "upload" and not os.getenv("TOKEN_JSON", "").strip():
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

    if PUBLISH_MODE == "upload":
        try:
            oauth_data = json.loads(os.environ["TOKEN_JSON"])
        except (json.JSONDecodeError, KeyError) as exc:
            raise RuntimeError("TOKEN_JSON is not valid JSON.") from exc

        if not oauth_data.get("refresh_token"):
            raise RuntimeError(
                "TOKEN_JSON must contain a valid OAuth refresh_token."
            )

    print("Configuration validated.")
    print("Gemini enabled:", bool(GEMINI_KEY))
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

def load_fallback_script():
    """Load a bundled Azerbaijani script when Gemini quota or service is unavailable."""
    fallback_path = BASE / "sample_script_10_facts_az.txt"
    if not fallback_path.exists():
        raise RuntimeError(
            "Gemini əlçatan deyil və ehtiyat ssenari faylı tapılmadı: "
            "sample_script_10_facts_az.txt"
        )
    script = fallback_path.read_text(encoding="utf-8").strip()
    word_count = len(re.findall(r"\b[\wƏəIıİiÖöÜüĞğŞşÇç]+\b", script, flags=re.UNICODE))
    if not 390 <= word_count <= 430:
        raise RuntimeError(
            f"Ehtiyat ssenarinin söz sayı uyğun deyil: {word_count}. "
            "sample_script_10_facts_az.txt faylını yoxlayın."
        )
    print(
        "WARNING: Gemini istifadə edilə bilmədi. "
        "Repo daxilindəki hazır Azərbaycan dilində ehtiyat ssenari istifadə olunur."
    )
    return script


def count_script_words(script):
    return len(re.findall(r"\b[\wƏəIıİiÖöÜüĞğŞşÇç]+\b", script, flags=re.UNICODE))


def generate_script(topic):
    language_names = {"az": "Azerbaijani", "en": "English", "tr": "Turkish"}
    language_name = language_names.get(LANGUAGE, "Azerbaijani")
    target_seconds = max(30, int(os.getenv("TARGET_VIDEO_SECONDS", "193")))
    topic_lower = topic.lower()
    is_brain_short = LANGUAGE == "az" and 40 <= target_seconds <= 60 and any(
        word in topic_lower for word in ("beyin", "brain", "neyron", "neuron")
    )
    brain_short_fallback = (
        "İnsan beyni bədənimizin idarəetmə mərkəzidir. O, nəfəs almaqdan yaddaşa "
        "qədər saysız-hesabsız prosesi koordinasiya edir. Birinci fakt: beyin özü "
        "ağrı reseptorlarına malik deyil, buna görə beyin toxuması birbaşa ağrı "
        "hiss etmir. İkinci: yuxu zamanı beyin dayanmaq əvəzinə məlumatları emal "
        "etməyə davam edir. Üçüncü: xatirələr video kimi saxlanmır; onları "
        "xatırlayanda beyin yenidən qurur. Dördüncü: öyrənmək neyronlar arasındakı "
        "əlaqələri dəyişə bilər. Beşinci: diqqət və yuxu yaddaşa ciddi təsir "
        "göstərir. Beyin haqqında ən maraqlı şey onun daim dəyişə bilməsidir. "
        "Bu səbəbdən yeni bacarıqlar öyrənmək və kifayət qədər yatmaq vacibdir. "
        "Sən bu faktlardan hansını ilk dəfə eşitdin? Şərhdə yaz!"
    )
    target_words = max(55, int(target_seconds * 2.05))
    min_words = max(45, int(target_words * 0.88))
    max_words = int(target_words * 1.12)
    print(f"1. Generating {language_name} script for: {topic}")
    # Optional local script override generated by the Windows Ollama integration.
    # The default Gemini path remains unchanged for existing GitHub Actions runs.
    override_path = os.getenv("SCRIPT_OVERRIDE_FILE", "").strip()
    if override_path:
        override_file = Path(override_path)
        if not override_file.is_file():
            raise RuntimeError("SCRIPT_OVERRIDE_FILE points to a missing file.")
        local_script = override_file.read_text(encoding="utf-8").strip()
        local_count = count_script_words(local_script)
        if not local_script or local_count < max(20, int(target_seconds * 0.55)):
            raise RuntimeError(f"Local script is empty or too short ({local_count} words).")
        print(f"Using local script override ({local_count} words); no Gemini request made.")
        return local_script
    prompt = f"""
Write a natural spoken YouTube narration in {language_name}.
Topic: {topic}
Target duration: {target_seconds} seconds. Aim for {min_words}-{max_words} words.
Use an engaging opening, accurate facts, short natural sentences, and a concise ending.
Do not invent statistics, citations or unsupported claims.
Return only the narration, without markdown, title, URL or stage directions.
"""
    try:
        script = generate_text(prompt)
    except Exception as exc:
        print(f"Gemini script generation failed: {exc}")
        if is_brain_short:
            script = brain_short_fallback
            print("WARNING: Gemini əlçatan deyil; beyin mövzusu üçün daxili 50 saniyəlik Azərbaycan ssenarisi istifadə olunur.")
        elif LANGUAGE == "az" and 150 <= target_seconds <= 220:
            script = load_fallback_script()
            global TOPIC
            TOPIC = "Elm və gündəlik həyatdan 10 maraqlı fakt"
        else:
            raise RuntimeError("Gemini əlçatan deyil və bu dil/müddət üçün ehtiyat ssenari yoxdur.") from exc
    word_count = count_script_words(script)
    if not min_words <= word_count <= max_words:
        try:
            correction = f"Revise this {language_name} narration to {min_words}-{max_words} words. Preserve factual accuracy and return only narration text:\n\n{script}"
            corrected = generate_text(correction)
            corrected_count = count_script_words(corrected)
            if min_words * 0.8 <= corrected_count <= max_words * 1.2:
                script, word_count = corrected, corrected_count
            elif is_brain_short:
                script = brain_short_fallback
                word_count = count_script_words(script)
            elif LANGUAGE == "az" and 150 <= target_seconds <= 220:
                script = load_fallback_script()
                word_count = count_script_words(script)
            else:
                raise RuntimeError(f"Script length {corrected_count} is outside the target range.")
        except Exception as exc:
            if is_brain_short:
                print(f"Correction unavailable, using built-in brain Shorts fallback: {exc}")
                script = brain_short_fallback
                word_count = count_script_words(script)
            elif LANGUAGE == "az" and 150 <= target_seconds <= 220:
                print(f"Correction unavailable, using bundled fallback: {exc}")
                script = load_fallback_script()
                word_count = count_script_words(script)
            else:
                raise
    if not int(min_words * 0.65) <= word_count <= int(max_words * 1.35):
        raise RuntimeError(f"Script has {word_count} words; target is approximately {min_words}-{max_words}.")
    print(f"Script word count: {word_count}")
    print(script)
    return script

def generate_metadata(script):
    """Create language-aware SEO metadata and save it for review."""
    topic = TOPIC.strip() or "interesting facts"
    topic_words = list(dict.fromkeys(re.findall(r"[A-Za-zƏəIıİiÖöÜüĞğŞşÇç]+", topic.lower())))
    if LANGUAGE == "en":
        title = f"{topic} | Interesting Facts"[:100]
        description = f"Discover interesting facts about {topic}. Watch to the end and share your thoughts.\n\nNARRATION:\n{script.strip()}\n\n#Facts #Learning #Science"
        tags = (topic_words + ["interesting facts", "educational", "science", "learn"])[:15]
    elif LANGUAGE == "tr":
        title = f"{topic} | İlginç Bilgiler"[:100]
        description = f"{topic} hakkında ilginç bilgiler. Sonuna kadar izleyin ve düşüncelerinizi yorumlarda paylaşın.\n\nVİDEO METNİ:\n{script.strip()}\n\n#İlginçBilgiler #Bilim #Öğren"
        tags = (topic_words + ["ilginç bilgiler", "eğitim", "bilim", "öğren"])[:15]
    else:
        title = f"{topic} | Maraqlı faktlar"[:100]
        description = f"{topic} haqqında maraqlı faktlar. Videonu sonadək izləyin və fikrinizi şərhdə yazın.\n\nVİDEODA SƏSLƏNƏN MƏTN:\n{script.strip()}\n\n#MaraqlıFaktlar #Azərbaycan #Elm"
        tags = (topic_words + ["10 maraqlı fakt", "maraqlı məlumatlar", "elm", "öyrən"])[:15]
    metadata = {"title": title, "description": description[:4900], "tags": tags, "language": LANGUAGE, "topic": topic}
    (WORK / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SEO metadata saved to work/metadata.json")
    return title, description[:4900], tags, []

def search_pexels(query):
    response = requests.get(
        "https://api.pexels.com/v1/videos/search",
        headers={"Authorization": PEXELS_KEY},
        params={
            "query": query,
            "orientation": "portrait" if VIDEO_FORMAT == "vertical" else "landscape",
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
    """Search stock providers with English query fallbacks; never fail solely because search returned zero results."""
    print("3. Searching available stock video providers...")

    providers = []
    if PEXELS_KEY and ("pexels" in STOCK_SOURCES or not STOCK_SOURCES):
        providers.append(search_pexels)
    if PIXABAY_KEY and ("pixabay" in STOCK_SOURCES or not STOCK_SOURCES):
        providers.append(search_pixabay)

    candidates = []
    seen = set()

    # Search terms should be English: stock libraries generally return much
    # better results for English than for Azerbaijani topic strings.
    topic_text = " ".join(str(q) for q in (queries or []))
    extra_queries = [
        "human brain neuroscience",
        "brain anatomy medical animation",
        "neuroscience science laboratory",
        "human thinking brain",
        "medical science research",
    ]
    all_queries = []
    for query in list(queries or []) + extra_queries:
        query = re.sub(r"[^A-Za-z0-9 ,'-]", " ", str(query)).strip()
        query = re.sub(r"\s+", " ", query)
        if query and query.lower() not in {q.lower() for q in all_queries}:
            all_queries.append(query)
    if not all_queries:
        all_queries = ["science laboratory", "medical science", "technology"]

    for query in all_queries:
        for search in providers:
            try:
                results = search(query)
                print(f"{search.__name__}: {len(results)} results for {query!r}")
                for item in results:
                    key = (item.get("source"), item.get("id") or item.get("url"))
                    if key not in seen:
                        seen.add(key)
                        candidates.append(item)
                if len(candidates) >= wanted * 3:
                    break
            except Exception as exc:
                print(f"Provider {search.__name__} failed for {query!r}: {exc}. Continuing.")
        if len(candidates) >= wanted * 3:
            break

    selected = []
    for item in candidates:
        path = WORK / f"stock_{len(selected) + 1}.mp4"
        try:
            print("Downloading:", item.get("source", "stock"), item.get("page", ""))
            download_file(item["url"], path)
            item["file"] = path
            selected.append(item)
            if len(selected) >= wanted:
                break
        except Exception as exc:
            print("Stock clip download failed; trying another clip:", exc)
            path.unlink(missing_ok=True)

    if selected:
        print(f"Selected {len(selected)} stock video(s).")
        return selected

    # Last-resort, locally generated abstract backgrounds. This ensures an API
    # zero-result/temporary outage does not crash the entire render job.
    print("WARNING: No usable stock clips found. Creating local FFmpeg fallback visuals.")
    fallback_items = []
    duration = max(8, min(15, int(os.getenv("TARGET_VIDEO_SECONDS", "50"))))
    colors = ["0x101B35", "0x162447", "0x203354", "0x172A3A", "0x242447"]
    for index in range(min(max(1, wanted), len(colors))):
        path = WORK / f"fallback_visual_{index + 1}.mp4"
        color = colors[index]
        try:
            run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i",
                f"color=c={color}:s=720x1280:r=25:d={duration}",
                "-vf", "format=yuv420p",
                "-an", "-c:v", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(path),
            ])
            fallback_items.append({
                "source": "Generated fallback",
                "url": "",
                "page": "",
                "creator": "Talyhs YouTube Automation (generated background)",
                "creator_url": "",
                "id": f"fallback-{index + 1}",
                "file": path,
            })
        except Exception as exc:
            path.unlink(missing_ok=True)
            print(f"Could not create fallback visual {index + 1}: {exc}")

    if not fallback_items:
        raise RuntimeError(
            "Stock providers returned no usable videos and FFmpeg could not create fallback visuals. "
            "Check FFmpeg installation and GitHub Actions logs."
        )
    print(f"Created {len(fallback_items)} fallback visual(s); continuing video production.")
    return fallback_items


def create_voice_and_subtitles(script):
    """Generate narration with ElevenLabs when configured, otherwise Edge TTS."""
    import asyncio
    import edge_tts

    if not script.strip():
        raise RuntimeError("Cannot synthesize an empty script.")

    provider = os.getenv("VOICE_PROVIDER", "auto").strip().lower()
    eleven_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    eleven_voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    eleven_model = os.getenv("ELEVENLABS_MODEL_ID", "eleven_v3").strip() or "eleven_v3"

    fliki_key = os.getenv("FLIKI_API_KEY", "").strip()
    fliki_voice_id = os.getenv("FLIKI_VOICE_ID", "").strip()
    fliki_style_id = os.getenv("FLIKI_VOICE_STYLE_ID", "").strip()

    if provider not in {"auto", "elevenlabs", "edge", "fliki"}:
        raise RuntimeError("VOICE_PROVIDER must be auto, elevenlabs, fliki or edge.")
    if provider == "fliki" and not (fliki_key and fliki_voice_id):
        raise RuntimeError("Fliki seçilib, amma FLIKI_API_KEY və FLIKI_VOICE_ID GitHub Secrets-də yoxdur.")

    use_elevenlabs = provider == "elevenlabs" or (
        provider == "auto" and bool(eleven_key and eleven_voice_id)
    )
    if provider == "elevenlabs" and not (eleven_key and eleven_voice_id):
        raise RuntimeError(
            "ElevenLabs seçilib, amma ELEVENLABS_API_KEY və/və ya "
            "ELEVENLABS_VOICE_ID GitHub Secrets-də yoxdur."
        )
    if bool(eleven_key) != bool(eleven_voice_id):
        raise RuntimeError(
            "ElevenLabs konfiqurasiyası natamamdır: ELEVENLABS_API_KEY və "
            "ELEVENLABS_VOICE_ID birlikdə verilməlidir."
        )

    if provider == "fliki":
        print("4. Fliki ilə Azərbaycan dilində AI səsləndirmə hazırlanır...")
        payload = {
            "content": script[:3000],
            "voiceId": fliki_voice_id,
            "sampleRate": 48000,
            "playbackRate": 1.0,
            "format": "mp3",
        }
        if fliki_style_id:
            payload["voiceStyleId"] = fliki_style_id
        response = requests.post(
            "https://api.fliki.ai/v1/generate/text-to-speech",
            headers={
                "Authorization": f"Bearer {fliki_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(20, 240),
        )
        if not response.ok:
            raise RuntimeError(
                f"Fliki TTS API xətası (HTTP {response.status_code}): "
                f"{response.text[:1000]}"
            )
        result = response.json()
        audio_url = result.get("audio")
        if not audio_url or not str(audio_url).startswith("https://"):
            raise RuntimeError("Fliki API etibarlı HTTPS audio URL qaytarmadı.")
        audio_response = requests.get(audio_url, timeout=(20, 240))
        audio_response.raise_for_status()
        AUDIO_FILE.write_bytes(audio_response.content)
        if not AUDIO_FILE.exists() or AUDIO_FILE.stat().st_size < 1000:
            raise RuntimeError("Fliki boş və ya yararsız audio faylı qaytardı.")
        original_duration = get_audio_duration()
        audio_duration = original_duration
        # Skip both ElevenLabs and Edge TTS after successful Fliki synthesis.
        use_elevenlabs = True
        print(f"Fliki səsi hazırdır: {audio_duration:.1f} saniyə.")

    if use_elevenlabs and provider != "fliki":
        print(f"4. ElevenLabs ilə yüksək keyfiyyətli səsləndirmə hazırlanır (model: {eleven_model})...")
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{eleven_voice_id}",
            headers={
                "xi-api-key": eleven_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            params={"output_format": "mp3_44100_128"},
            json={
                "text": script,
                "model_id": eleven_model,
                "voice_settings": {
                    "stability": 0.50,
                    "similarity_boost": 0.78,
                    "style": 0.20,
                    "use_speaker_boost": True
                }
            },
            timeout=(20, 240),
        )
        if not response.ok:
            # Never expose credentials. If the key lacks TTS permission, continue
            # with Edge TTS so a permissions mistake does not abort video creation.
            detail = response.text[:1200]
            missing_tts_permission = response.status_code == 401 and (
                "text_to_speech" in detail or "missing_permissions" in detail
            )
            missing_voice = response.status_code == 404 and (
                "voice_not_found" in detail or "not_found" in detail
            )
            if missing_tts_permission:
                print(
                    "WARNING: ElevenLabs API key lacks text_to_speech permission. "
                    "Falling back to Edge TTS; update the key permissions to restore ElevenLabs."
                )
                use_elevenlabs = False
            elif missing_voice:
                print(
                    "WARNING: ElevenLabs voice ID was not found or is not accessible to this API key. "
                    "Falling back to Edge TTS. Check ELEVENLABS_VOICE_ID and voice access in ElevenLabs."
                )
                use_elevenlabs = False
            else:
                raise RuntimeError(
                    f"ElevenLabs API xətası (HTTP {response.status_code}): {detail}"
                )
        if use_elevenlabs:
            AUDIO_FILE.write_bytes(response.content)
            if not AUDIO_FILE.exists() or AUDIO_FILE.stat().st_size < 1000:
                raise RuntimeError("ElevenLabs boş və ya yararsız audio qaytardı.")
            original_duration = get_audio_duration()
            audio_duration = original_duration
            print(
                f"ElevenLabs səsi hazırdır: {audio_duration:.1f} saniyə. "
                "Təbii tələffüzü qorumaq üçün səs sürətləndirilmir."
            )

    if not use_elevenlabs:
        print(f"4. Edge TTS ilə səsləndirmə hazırlanır ({VOICE})...")
        async def synthesize():
            communicate = edge_tts.Communicate(script, VOICE, rate="+0%")
            await communicate.save(str(AUDIO_FILE))

        try:
            # Edge TTS may return HTTP 403 on hosted runners. Retry once, then
            # use the locally installed espeak-ng engine so the scheduled job
            # can still produce a video instead of failing before upload.
            try:
                asyncio.run(synthesize())
            except Exception as edge_error:
                print(
                    f"WARNING: Edge TTS failed ({edge_error}). "
                    "Trying local espeak-ng fallback."
                )
                wav_file = WORK / "voiceover_fallback.wav"
                fallback_voice = "en-us" if LANGUAGE == "en" else "tr"
                run([
                    "espeak-ng", "-v", fallback_voice, "-s", "145",
                    "-w", str(wav_file), script
                ])
                if not wav_file.exists() or wav_file.stat().st_size < 1000:
                    raise RuntimeError("espeak-ng did not create a valid fallback WAV.")
                run([
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(wav_file), "-codec:a", "libmp3lame", "-q:a", "3",
                    str(AUDIO_FILE)
                ])
                wav_file.unlink(missing_ok=True)
                print(
                    "WARNING: Local fallback narration is active. "
                    "It may not pronounce Azerbaijani as naturally as neural TTS."
                )
        except Exception as exc:
            raise RuntimeError(
                f"Edge TTS and local fallback both failed: {exc}"
            ) from exc

        if not AUDIO_FILE.exists() or AUDIO_FILE.stat().st_size == 0:
            raise RuntimeError("TTS did not create an audio file.")

        # Keep legacy Edge TTS duration fitting; ElevenLabs audio is never time-stretched.
        target_duration = float(os.getenv("TARGET_VIDEO_SECONDS", "193"))
        original_duration = get_audio_duration()
        tempo = original_duration / target_duration
        if not 0.25 <= tempo <= 4.0:
            raise RuntimeError(
                f"Səsləndirmə müddəti ({original_duration:.1f}s) hədəf müddətdən "
                "həddindən artıq fərqlənir. Ssenarinin söz sayını yoxlayın."
            )

        tempo_factors = []
        remaining_tempo = tempo
        while remaining_tempo < 0.5:
            tempo_factors.append(0.5)
            remaining_tempo /= 0.5
        while remaining_tempo > 2.0:
            tempo_factors.append(2.0)
            remaining_tempo /= 2.0
        tempo_factors.append(remaining_tempo)
        tempo_filter = ",".join(f"atempo={factor:.6f}" for factor in tempo_factors)

        adjusted_audio = WORK / "voiceover_adjusted.mp3"
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(AUDIO_FILE),
            "-filter:a", tempo_filter,
            "-t", f"{target_duration:.3f}",
            "-codec:a", "libmp3lame", "-q:a", "3",
            str(adjusted_audio),
        ])
        adjusted_audio.replace(AUDIO_FILE)
        audio_duration = get_audio_duration()
        print(f"Edge TTS səs müddəti: {audio_duration:.1f} saniyə.")


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
        "PlayResX: " + ("1080" if VIDEO_FORMAT == "vertical" else "1920"),
        "PlayResY: " + ("1920" if VIDEO_FORMAT == "vertical" else "1080"),
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
    """Build a normalized timeline with MLT (Shotcut's engine), then mux narration/subtitles."""
    import shutil
    import xml.etree.ElementTree as ET

    if not clips:
        raise RuntimeError("Cannot render a video without stock clips.")

    print("5. Editing stock footage with the MLT engine used by Shotcut...")
    scene_duration = float(duration) / len(clips)
    width, height = (1080, 1920) if VIDEO_FORMAT == "vertical" else (1920, 1080)
    fps = 30
    normalized = []

    for index, clip in enumerate(clips):
        output = WORK / f"scene_{index:02}.mp4"
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-stream_loop", "-1", "-i", str(clip["file"]),
            "-t", f"{scene_duration:.3f}",
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps},setsar=1",
            "-an", "-c:v", "libx264", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(output),
        ])
        normalized.append(output)

    montage_file = WORK / "mlt_montage.mp4"
    melt = shutil.which("melt")
    if melt:
        # MLT XML describes a real edit timeline: each normalized stock clip is a
        # separate producer placed consecutively on one playlist, as in Shotcut.
        profile = ET.Element("profile", {
            "description": "Talyhs Studio HD timeline",
            "width": str(width), "height": str(height), "progressive": "1",
            "frame_rate_num": str(fps), "frame_rate_den": "1",
            "sample_aspect_num": "1", "sample_aspect_den": "1",
            "display_aspect_num": str(width), "display_aspect_den": str(height),
            "colorspace": "709",
        })
        root = ET.Element("mlt", {"LC_NUMERIC": "C", "version": "7.0.0", "title": "Talyhs Studio automatic edit"})
        root.append(profile)
        entries = []
        total_frames = 0
        for index, scene in enumerate(normalized):
            producer_id = f"producer{index}"
            out_frame = max(0, int(round(scene_duration * fps)) - 1)
            producer = ET.SubElement(root, "producer", {
                "id": producer_id, "in": "0", "out": str(out_frame),
            })
            ET.SubElement(producer, "property", {"name": "resource"}).text = str(scene.resolve())
            ET.SubElement(producer, "property", {"name": "mlt_service"}).text = "avformat"
            ET.SubElement(producer, "property", {"name": "audio_index"}).text = "-1"
            entries.append({
                "producer": producer_id, "in": "0", "out": str(out_frame),
            })
            total_frames += out_frame + 1

        # MLT producers must be declared before the playlist that references them.
        playlist = ET.SubElement(root, "playlist", {"id": "playlist0"})
        for entry_attrs in entries:
            ET.SubElement(playlist, "entry", entry_attrs)

        timeline_file = WORK / "shotcut_mlt_timeline.mlt"
        ET.ElementTree(root).write(timeline_file, encoding="utf-8", xml_declaration=True)
        print(f"MLT timeline created: {timeline_file} ({len(normalized)} clips, {total_frames} frames)")
        try:
            run([
                melt, str(timeline_file),
                "-consumer", f"avformat:{montage_file}",
                "vcodec=libx264", "crf=21", "preset=veryfast",
                "pix_fmt=yuv420p", "real_time=-1",
            ])
        except Exception as exc:
            raise RuntimeError(
                "MLT (Shotcut engine) could not render the timeline. "
                "Check the MLT installation and runner logs. Original error: " + str(exc)
            ) from exc
    else:
        # Keep the pipeline usable on local machines without MLT; GitHub Actions
        # installs melt and therefore uses the MLT/Shotcut timeline above.
        print("WARNING: 'melt' was not found; using the FFmpeg concat fallback.")
        concat_file = WORK / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{p.resolve().as_posix()}'\n" for p in normalized),
            encoding="utf-8",
        )
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-an", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-movflags", "+faststart", str(montage_file),
        ])

    if not montage_file.exists() or montage_file.stat().st_size == 0:
        raise RuntimeError("MLT/FFmpeg did not create the montage MP4.")

    # Burn the existing ASS subtitles after the MLT montage and add Edge-TTS audio.
    subtitle_path = SUBTITLE_FILE.resolve().as_posix()
    subtitle_path = subtitle_path.replace("\\", r"\\").replace(":", r"\:")
    subtitle_path = subtitle_path.replace("'", r"\'")
    filter_arg = f"subtitles='{subtitle_path}'" if ADD_SUBTITLES else "null"

    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(montage_file), "-i", str(AUDIO_FILE),
        "-vf", filter_arg,
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", f"{float(duration):.3f}", "-r", str(fps),
        "-c:v", "libx264", "-preset", "medium", "-crf", "21",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", str(VIDEO_FILE),
    ])

    if not VIDEO_FILE.exists() or VIDEO_FILE.stat().st_size == 0:
        raise RuntimeError("Final MP4 was not created.")

def validate_final_video(expected_duration):
    """Fail closed if the rendered MP4 has no usable video/audio or wrong duration."""
    if not VIDEO_FILE.exists() or VIDEO_FILE.stat().st_size < 100_000:
        raise RuntimeError("Final MP4 is missing or suspiciously small.")
    raw = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(VIDEO_FILE)])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ffprobe returned invalid JSON for the final MP4.") from exc
    streams = data.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if not video or not audio:
        raise RuntimeError("Quality check failed: final MP4 must contain both video and audio streams.")
    actual = float((data.get("format") or {}).get("duration", 0) or 0)
    if actual <= 0 or abs(actual - float(expected_duration)) > 3.0:
        raise RuntimeError(f"Quality check failed: duration {actual:.2f}s differs from target {expected_duration:.2f}s.")
    expected = (1080, 1920) if VIDEO_FORMAT == "vertical" else (1920, 1080)
    actual_size = (int(video.get("width", 0)), int(video.get("height", 0)))
    if actual_size != expected:
        raise RuntimeError(f"Quality check failed: expected {expected[0]}x{expected[1]}, got {actual_size[0]}x{actual_size[1]}.")
    print(f"Quality check passed: {actual_size[0]}x{actual_size[1]}, {actual:.1f}s, video+audio streams present.")
def create_thumbnail(title):
    """Generate a topic-specific thumbnail with AUTOMATIC1111 when configured."""
    import base64
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont

    output = WORK / "thumbnail.jpg"
    width, height = 1280, 720
    sd_url = os.getenv("SD_WEBUI_URL", "").strip().rstrip("/")
    sd_username = os.getenv("SD_WEBUI_USERNAME", "").strip()
    sd_password = os.getenv("SD_WEBUI_PASSWORD", "").strip()
    topic = TOPIC.strip() or title

    def load_fonts():
        try:
            return (
                ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 68),
                ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26),
            )
        except OSError:
            fallback = ImageFont.load_default()
            return fallback, fallback

    image = None
    if sd_url:
        print("Generating thumbnail background with AUTOMATIC1111 Stable Diffusion WebUI...")
        prompt = (
            f"Create a premium, cinematic YouTube thumbnail background about: {topic}. "
            "Landscape 16:9 composition, photorealistic, dramatic studio lighting, "
            "high contrast, rich deep navy and teal colors with warm golden highlights, "
            "one clear visually striking subject related to the topic positioned on the "
            "right half, clean dark negative space on the left for a large title overlay, "
            "professional editorial photography, crisp details, polished composition. "
            "No text, no letters, no words, no logos, no watermark, no collage, no border."
        )
        negative_prompt = (
            "text, typography, letters, words, watermark, logo, signature, blurry, "
            "low resolution, deformed, distorted, duplicate subject, cluttered layout, "
            "oversaturated, artifacts, frame, border"
        )
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": int(os.getenv("SD_WEBUI_STEPS", "25")),
            "cfg_scale": 7,
            "sampler_name": os.getenv("SD_WEBUI_SAMPLER", "DPM++ 2M Karras"),
            "batch_size": 1,
            "n_iter": 1,
            "restore_faces": False,
            "send_images": True,
            "save_images": False,
        }
        try:
            response = requests.post(
                f"{sd_url}/sdapi/v1/txt2img",
                json=payload,
                auth=(sd_username, sd_password) if sd_username or sd_password else None,
                timeout=(20, 300),
            )
            response.raise_for_status()
            result = response.json()
            images = result.get("images") or []
            if not images:
                raise RuntimeError("AUTOMATIC1111 returned no images.")
            encoded = images[0].split(",", 1)[-1]
            generated = Image.open(BytesIO(base64.b64decode(encoded))).convert("RGB")
            # Keep the composition exactly 16:9 for YouTube thumbnails.
            generated = generated.resize((width, height), Image.Resampling.LANCZOS)
            image = generated
            print("AUTOMATIC1111 background generated successfully.")
        except Exception as exc:
            if os.getenv("SD_WEBUI_REQUIRED", "false").strip().lower() == "true":
                raise RuntimeError(
                    "AUTOMATIC1111 thumbnail generation failed and SD_WEBUI_REQUIRED=true. "
                    "Check SD_WEBUI_URL, API access, credentials, model and available VRAM. "
                    f"Original error: {exc}"
                ) from exc
            print(f"WARNING: AUTOMATIC1111 unavailable; using branded Pillow fallback: {exc}")

    if image is None:
        image = Image.new("RGB", (width, height), (14, 22, 40))
        draw = ImageDraw.Draw(image)
        for i in range(12):
            x = i * 125 - 180
            draw.polygon(
                [(x, 0), (x + 260, 0), (x + 520, height), (x + 260, height)],
                fill=(22 + i % 3 * 5, 47 + i % 4 * 4, 78 + i % 5 * 4),
            )

    # Add the title in Pillow, since diffusion models are unreliable at rendering text.
    draw = ImageDraw.Draw(image)
    font, small = load_fonts()
    words = title[:64].split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] > 700 and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)

    # Darken the left side to preserve readable contrast over any generated image.
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    from PIL import Image as PILImage
    shade = PILImage.new("RGBA", (width, height), (0, 0, 0, 0))
    shade_pixels = shade.load()
    for x in range(0, 820):
        alpha = int(165 * (1 - x / 820))
        for y in range(height):
            shade_pixels[x, y] = (5, 10, 22, alpha)
    image = Image.alpha_composite(image.convert("RGBA"), shade).convert("RGB")
    draw = ImageDraw.Draw(image)

    y = max(70, (height - min(len(lines), 4) * 86) // 2)
    for line in lines[:4]:
        draw.text((72, y + 5), line, font=font, fill=(0, 0, 0), stroke_width=3, stroke_fill=(0, 0, 0))
        draw.text((68, y), line, font=font, fill=(255, 255, 255), stroke_width=2, stroke_fill=(10, 18, 30))
        y += 86
    draw.rounded_rectangle((68, 620, 390, 675), radius=14, fill=(255, 197, 44))
    draw.text((88, 634), "TALYHS STUDIO", font=small, fill=(14, 22, 40))
    image.save(output, "JPEG", quality=92, optimize=True)
    print("Thumbnail created:", output)


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
            "defaultLanguage": LANGUAGE if LANGUAGE in {"az", "en", "tr"} else "az",
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
    requested_topic = os.getenv("VIDEO_TOPIC", "").strip()
    if requested_topic:
        TOPIC = requested_topic
        topic_lower = requested_topic.lower()
        if any(word in topic_lower for word in ("beyin", "brain", "neuron", "neyron")):
            stock_queries = [
                "human brain neuroscience animation",
                "brain neurons medical visualization",
                "human brain anatomy 3d",
                "person thinking close up",
            ]
        else:
            stock_queries = [
                requested_topic,
                requested_topic + " science",
                requested_topic + " educational video",
            ]
    else:
        TOPIC, stock_queries = get_daily_topic()
    print("Topic:", TOPIC)
    print("Language:", LANGUAGE, "Format:", VIDEO_FORMAT, "Publish mode:", PUBLISH_MODE)
    print("Gemini model:", MODEL)
    print("TTS voice:", VOICE)

    check_configuration()
    script = generate_script(TOPIC)
    title, description, tags, metadata_queries = generate_metadata(script)
    queries = stock_queries or metadata_queries
    clips = collect_clips(queries, wanted=5)
    duration = create_voice_and_subtitles(script)
    make_video(clips, duration)
    validate_final_video(duration)
    if CREATE_THUMBNAIL:
        create_thumbnail(title)
    if PUBLISH_MODE == "upload":
        video_id = upload_video(title, description, tags, clips)
        if CREATE_THUMBNAIL:
            try:
                youtube = get_youtube_service()
                youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(WORK / "thumbnail.jpg"), mimetype="image/jpeg")).execute()
                print("Custom thumbnail uploaded.")
            except Exception as exc:
                print("Thumbnail upload failed; video remains uploaded:", exc)
    else:
        print("PUBLISH_MODE=prepare: MP4 was rendered but not uploaded.")
    print("Final title:", title)
    print("SEO metadata:", WORK / "metadata.json")

    print("Final MP4:", VIDEO_FILE)
    print("Subtitles:", SUBTITLE_FILE)


if __name__ == "__main__":
    main()
