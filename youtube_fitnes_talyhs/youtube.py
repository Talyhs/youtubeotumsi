#!/usr/bin/env python3
"""Turkish-language fitness YouTube Shorts automation."""
from __future__ import annotations
import asyncio, json, os, random, re, shutil, subprocess, sys, time
from pathlib import Path
import requests
import edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
try:
    from .quality import create_thumbnail, validate_video, write_review_manifest
except ImportError:  # Running this file directly from the module directory
    from quality import create_thumbnail, validate_video, write_review_manifest

ROOT = Path(__file__).resolve().parent
OUT, TMP = ROOT / "output", ROOT / "tmp"
OUT.mkdir(exist_ok=True); TMP.mkdir(exist_ok=True)
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
TOKEN_JSON = os.getenv("TOKEN_JSON", "")
CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID", "").strip()
MODE = os.getenv("PUBLISH_MODE", "prepare").lower()
SECONDS = max(30, min(60, int(os.getenv("VIDEO_SECONDS", "45"))))
VOICE = os.getenv("EDGE_TTS_VOICE", "tr-TR-EmelNeural")
REQUESTED_TOPIC = os.getenv("FITNESS_TOPIC", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
ALLOW_PUBLIC = os.getenv("ALLOW_PUBLIC_UPLOAD", "NO").upper() == "YES"
CONFIRM_UPLOAD = os.getenv("CONFIRM_UPLOAD", "NO").upper() == "YES"

IDEAS = [
    ("Şınavda Yapılan 3 Hata", "beginner push-up form demonstration"),
    ("Antrenman Öncesi Basit Isınma", "safe beginner warm-up exercises"),
    ("Squat Nasıl Doğru Yapılır?", "bodyweight squat technique demonstration"),
    ("Dinlenme Günleri Neden Önemli?", "fitness recovery rest day"),
    ("Düzenli Egzersiz Alışkanlığı Nasıl Kazanılır?", "beginner home workout routine"),
    ("Antrenmanda Su İçmek Neden Önemli?", "athlete drinking water during workout"),
    ("Ekipmansız Evde Antrenman", "beginner bodyweight exercises at home"),
]
def run(cmd: list[str]) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, text=True, capture_output=True)
    if p.returncode:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr[-2500:]}")
    return p

def gen_json(prompt: str):
    if not GEMINI_API_KEY: return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"
    try:
        r = requests.post(url, json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.7,"responseMimeType":"application/json"}}, timeout=60)
        r.raise_for_status(); raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        match = re.search(r"\{.*\}", raw, re.S)
        return json.loads(match.group(0) if match else raw)
    except Exception as e:
        print(f"WARNING: AI script generation unavailable; using fallback. {e}")
        return None

def script_word_count(text):
    """Count spoken words for duration-aware narration checks."""
    return len(re.findall(r"\b[\w]+(?:['’-][\w]+)*\b", str(text)))


def target_word_range(seconds):
    """Comfortable narration pace for a 30, 45, or 60 second Short."""
    if seconds <= 30:
        return 52, 72
    if seconds <= 45:
        return 82, 105
    return 112, 135


def fallback_script(topic):
    """Readable, safety-conscious fallback with length matched to the selected duration."""
    sentences = [
        f"Bugün {topic} konusuna odaklanıyoruz.",
        "Kendini rahat hissettiğin bir tempoda başla ve kontrol edebildiğin hareketleri seç.",
        "Duruşunu koru, hareketleri kontrollü yap ve her tekrarda nefes alıp ver.",
        "Başlamadan önce birkaç kolay hareketle ısın.",
        "Hareket tekniğin bozulmaya başlarsa yavaşla veya kısa bir mola ver.",
        "Düzenli egzersiz alışkanlığı kazanmak için kendini sonuna kadar zorlaman gerekmez.",
        "Mevcut kondisyonuna ve çalışma alanına uygun hareketler seç.",
        "Keskin ağrı, baş dönmesi veya alışılmadık bir rahatsızlık hissedersen dur.",
        "Vücuduna toparlanması için zaman tanı, su iç ve yeterince uyu.",
        "Zaman içinde düzenli çalışmak, tek seferde aşırı zorlanmaktan daha faydalıdır.",
        "Her tekrarı aceleyle yapmak yerine doğru ve kontrollü tekniğe odaklan.",
        "Bu öneriyi bir sonraki antrenmanında dene ve daha fazla fitness tavsiyesi için takip et.",
    ]
    target = round(SECONDS * 2.0)
    chosen = []
    for sentence in sentences:
        chosen.append(sentence)
        if script_word_count(" ".join(chosen)) >= target:
            break
    return " ".join(chosen)


def topic_data():
    title, topic = IDEAS[int(time.time() // 14400) % len(IDEAS)]
    if REQUESTED_TOPIC:
        title = REQUESTED_TOPIC[:90]
        topic = REQUESTED_TOPIC[:180]

    min_words, max_words = target_word_range(SECONDS)
    target_words = round((min_words + max_words) / 2)
    prompt = (
        "Türkçe içerik üreten deneyimli bir fitness yazarı ve titiz editör gibi davran. "
        "Bir YouTube Fitness Shorts videosu için özgün içerik oluştur ve yalnızca şu anahtarlarla geçerli JSON döndür: "
        "title, topic, script, search_terms (array of 3-5 strings), description, hashtags (array). "
        f"Konu: {topic}. Süre: {SECONDS} saniye. Konuşma metni mutlaka {min_words}-{max_words} kelime olsun "
        f"(hedef yaklaşık {target_words} kelime); seslendirme video süresine sığmalıdır. "
        "Metni doğal, akıcı ve doğru Türkiye Türkçesiyle yaz; dil bilgisi, yazım ve noktalama kurallarına uy. "
        "Metni sesli okunuyormuş gibi kontrol et; yapay, tekrarlı veya çeviri gibi duran cümleleri düzelt. "
        "Farklı cümle başlangıçları, kısa ve seslendirmeye uygun ifadeler kullan; ilk cümlede dikkat çekici bir giriş yap. "
        "Yapı: dikkat çekici giriş, tek ve net bir pratik öneri, uygulanabilir kısa açıklama, gerektiğinde güvenlik uyarısı ve doğal takip çağrısı. "
        "Konuşma metninde yalnızca anlatıcının söyleyeceği sözler bulunsun; başlık, sahne yönergesi, emoji veya madde işareti ekleme. "
        "Her öneri konuya özel olsun; istatistik uydurma, sonuç garantisi verme, bedenleri aşağılamama ve tıbbi tavsiye sunma. "
        "İddialar gerçekçi ve başlangıç seviyesine uygun olsun. Başlık kısa, doğru ve yanıltıcı olmayan şekilde ilgi çekici olsun. "
        "Açıklama doğal Türkçe olsun ve videoda anlatılanları doğru biçimde özetlesin. "
        "search_terms alanındaki arama ifadelerini Pexels ve Pixabay'de daha iyi sonuç için İngilizce yaz; tam konuya uygun gerçek görüntüler tarif et, alakasız genel spor salonu klipleri kullanma. "
        "Yalnızca geçerli JSON döndür; Markdown kod çiti veya ek açıklama ekleme."
    )
    data = gen_json(prompt)

    def valid_payload(item):
        return (
            isinstance(item, dict)
            and all(k in item for k in ("title", "script", "search_terms"))
            and isinstance(item.get("title"), str) and bool(item["title"].strip())
            and isinstance(item.get("script"), str) and bool(item["script"].strip())
        )

    if valid_payload(data):
        count = script_word_count(data["script"])
        if not min_words <= count <= max_words:
            print(f"INFO: Revising narration length ({count} words; target {min_words}-{max_words}).")
            revised = gen_json(
                "Bu fitness Shorts metnini akıcı ve doğal Türkiye Türkçesiyle yeniden yaz. "
                f"The final spoken script must contain {min_words}-{max_words} words, with no headings or stage directions. "
                "Güvenli ve doğru önerileri ve aynı konuyu koru. Yalnızca aynı JSON anahtarlarını döndür. "
                f"JSON to revise: {json.dumps(data, ensure_ascii=False)}"
            )
            if valid_payload(revised) and min_words <= script_word_count(revised["script"]) <= max_words:
                data = revised
            else:
                data = None

    if valid_payload(data) and min_words <= script_word_count(data["script"]) <= max_words:
        data["title"] = data["title"].strip()[:90]
        data["topic"] = str(data.get("topic") or topic).strip()[:180]
        data["script"] = data["script"].strip()
        data["description"] = str(data.get("description") or "Başlangıç seviyesine uygun fitness önerileri.").strip()
        if not isinstance(data.get("search_terms"), list):
            data["search_terms"] = [str(data["search_terms"])]
        data["search_terms"] = [str(x).strip() for x in data["search_terms"] if str(x).strip()][:5]
        if not data["search_terms"]:
            data["search_terms"] = fallback_footage_terms(topic, data["title"])
        if not isinstance(data.get("hashtags"), list):
            data["hashtags"] = ["#fitness", "#shorts", "#antrenman"]
        data["hashtags"] = [str(x).strip() for x in data["hashtags"] if str(x).strip()][:8]
        if not data["hashtags"]:
            data["hashtags"] = ["#fitness", "#shorts", "#antrenman"]
        print(f"Turkish script quality gate: {script_word_count(data['script'])} words; target {min_words}-{max_words}.")
        return data

    print("UYARI: Yapay zekâ metni oluşturulamadı veya süre/kalite kontrolünü geçemedi; kontrol edilmiş Türkçe yedek metin kullanılacak.")
    return {
        "title": title, "topic": topic,
        "script": fallback_script(topic),
        "search_terms": fallback_footage_terms(topic, title),
        "description": f"{topic} hakkında başlangıç seviyesine uygun pratik öneriler. Kendine uygun hareketleri seç ve ağrı hissedersen dur.",
        "hashtags": ["#fitness", "#shorts", "#antrenman", "#egzersiz"]
    }

def fallback_footage_terms(topic, title=""):
    """Map common Turkish topic wording to English stock-search phrases."""
    text = f"{title} {topic}".casefold()
    if any(word in text for word in ("şınav", "push-up", "push up")):
        return ["proper push-up form demonstration", "person doing push-ups side view", "push-up mistakes exercise technique"]
    if any(word in text for word in ("squat", "çömel")):
        return ["bodyweight squat proper form", "person demonstrating squat exercise", "squat technique side view"]
    if any(word in text for word in ("ısınma", "ısın", "warm-up", "warmup")):
        return ["beginner dynamic warm-up exercises", "athlete warming up before workout", "dynamic stretching exercise demonstration"]
    if any(word in text for word in ("dinlen", "toparlan", "recovery", "rest day")):
        return ["athlete resting after workout", "fitness recovery stretching", "rest day recovery exercise"]
    if any(word in text for word in ("su iç", "hidrasyon", "susuz", "water")):
        return ["athlete drinking water during workout", "hydration after exercise", "person drinking water at gym"]
    if any(word in text for word in ("ekipmansız", "evde", "home workout", "ekipman")):
        return ["beginner bodyweight workout at home", "person exercising at home no equipment", "home fitness workout demonstration"]
    if any(word in text for word in ("karın", "abs", "plank")):
        return ["proper plank exercise form", "beginner abdominal workout demonstration", "core exercise proper technique"]
    return ["beginner fitness exercise demonstration", "person demonstrating correct workout form", "bodyweight exercise technique"]


def parse_list(value):
    if isinstance(value, list): return [str(x).strip() for x in value if str(x).strip()]
    try:
        obj=json.loads(value)
        if isinstance(obj,list): return [str(x).strip() for x in obj if str(x).strip()]
    except Exception: pass
    return [x.strip() for x in re.split(r"[,;]", str(value)) if x.strip()]

def pexels(q):
    if not PEXELS_API_KEY: return []
    r=requests.get("https://api.pexels.com/videos/search",headers={"Authorization":PEXELS_API_KEY},params={"query":q,"orientation":"portrait","per_page":10},timeout=30); r.raise_for_status()
    out=[]
    for v in r.json().get("videos",[]):
        files=[f for f in v.get("video_files",[]) if f.get("link") and f.get("file_type")=="video/mp4"]
        if files:
            files.sort(key=lambda f:(f.get("width",0)<f.get("height",0),f.get("width",0)),reverse=True)
            out.append({"url":files[0]["link"],"credit":f"Pexels video by {v.get('user',{}).get('name','creator')}","page":v.get("url","") ,"query":q,"tags":[]})
    return out

def pixabay(q):
    if not PIXABAY_API_KEY: return []
    r=requests.get("https://pixabay.com/api/videos/",params={"key":PIXABAY_API_KEY,"q":q,"per_page":10,"safesearch":"true"},timeout=30); r.raise_for_status()
    out=[]
    for v in r.json().get("hits",[]):
        variants=v.get("videos",{}); f=variants.get("medium") or variants.get("small") or variants.get("large")
        if f and f.get("url"): out.append({"url":f["url"],"credit":f"Pixabay video by {v.get('user','creator')}","page":v.get("pageURL","") ,"query":q,"tags":parse_list(v.get('tags',''))})
    return out

def footage_queries(data):
    """Build specific search queries from the actual topic, not generic gym footage."""
    topic = str(data.get("topic") or data.get("title") or "beginner fitness").strip()
    title = str(data.get("title") or topic).strip()
    supplied = parse_list(data.get("search_terms", []))
    candidates = supplied[:2] + [f"{topic} exercise demonstration", f"{title} proper form"] + supplied[2:]
    result, seen = [], set()
    for query in candidates:
        query = re.sub(r"\s+", " ", str(query)).strip()
        key = query.casefold()
        if not query or key in seen:
            continue
        seen.add(key)
        result.append(query[:100])
        if len(result) >= 4:
            break
    return result or [f"{topic} exercise demonstration"]


def download_clips(terms):
    """Search by topic-specific terms, interleave query results, and reject tagged mismatches."""
    queries = parse_list(terms)[:4]
    if not queries:
        raise RuntimeError("No topic-specific stock footage search terms were generated.")
    groups = []
    for query in queries:
        group = []
        for provider in (pexels, pixabay):
            try:
                group.extend(provider(query))
            except Exception as exc:
                print(f"WARNING: stock search error for '{query}': {exc}")
        # Preserve provider ranking; deduplicate within each query group.
        seen_urls = set()
        group = [item for item in group if item.get("url") and not (
            item["url"] in seen_urls or seen_urls.add(item["url"])
        )]
        groups.append(group)

    # Round-robin query results so the montage can cover different aspects of the same topic.
    all_clips = []
    max_items = max((len(group) for group in groups), default=0)
    for index in range(max_items):
        for group in groups:
            if index < len(group):
                all_clips.append(group[index])

    used, paths, credits = set(), [], []
    for clip in all_clips:
        if clip["url"] in used:
            continue
        tags = " ".join(clip.get("tags", [])).lower()
        query_words = {w.replace("-", "") for w in re.findall(r"[a-z0-9-]+", clip.get("query", "").lower()) if len(w) > 2}
        tag_words = {w.replace("-", "") for w in re.findall(r"[a-z0-9-]+", tags) if len(w) > 2}
        if tag_words and query_words and not (query_words & tag_words):
            print(f"INFO: rejecting low-relevance Pixabay clip for query '{clip.get('query', '')}'.")
            continue
        used.add(clip["url"])
        path = TMP / f"clip_{len(paths)+1}.mp4"
        try:
            with requests.get(clip["url"], stream=True, timeout=90) as response:
                response.raise_for_status()
                with path.open("wb") as file_obj:
                    for chunk in response.iter_content(512 * 1024):
                        if chunk:
                            file_obj.write(chunk)
            probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
            if float(probe.stdout.strip() or 0) < 0.5:
                raise RuntimeError("stock clip is shorter than 0.5 seconds")
            paths.append(path)
            credits.append(f"- {clip['credit']}: {clip['page']}")
            print(f"Selected footage for '{clip.get('query', 'topic')}': {clip['page']}")
            if len(paths) >= 5:
                break
        except Exception as exc:
            path.unlink(missing_ok=True)
            print(f"WARNING: skipping invalid stock clip: {exc}")
    if not paths:
        raise RuntimeError("No relevant stock clips downloaded. Add PEXELS_API_KEY and/or PIXABAY_API_KEY, then review the search terms.")
    return paths, credits

async def make_voice(script):
    path=TMP/"voice.mp3"
    await edge_tts.Communicate(script,VOICE,rate="-10%").save(str(path))
    if not path.exists() or path.stat().st_size<1000: raise RuntimeError("Could not generate voice audio")
    return path

def timestamp(sec):
    ms=int(max(0,sec)*1000); h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); s,ms=divmod(ms,1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def ass_timestamp(sec):
    cs = int(max(0, sec) * 100)
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_escape(text):
    return str(text).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def caption_chunks(words, max_words=5, max_chars=34):
    """Make quick-reading caption beats, normally 3–5 words each."""
    chunks, current = [], []
    chars = 0
    for word in words:
        extra = len(word) + (1 if current else 0)
        if current and (len(current) >= max_words or chars + extra > max_chars):
            chunks.append(current)
            current, chars = [], 0
        current.append(word)
        chars += len(word) + (1 if len(current) > 1 else 0)
    if current:
        chunks.append(current)
    return chunks


def whisper_word_timings(audio_path):
    """Return real word timestamps from Whisper when explicitly enabled."""
    if os.getenv("USE_WHISPER_CAPTIONS", "NO").upper() != "YES":
        return None
    try:
        import whisper
        model = whisper.load_model(os.getenv("WHISPER_MODEL", "base"))
        result = model.transcribe(str(audio_path), word_timestamps=True, fp16=False)
        timed = []
        for segment in result.get("segments", []):
            for word in segment.get("words", []):
                token = str(word.get("word", "")).strip()
                if token:
                    timed.append({
                        "word": token,
                        "start": max(0.0, float(word.get("start", 0))),
                        "end": max(float(word.get("start", 0)) + 0.04, float(word.get("end", 0))),
                    })
        if timed:
            print(f"Whisper word alignment enabled: {len(timed)} timed words.")
            return timed
        print("WARNING: Whisper returned no word timestamps; using estimated caption timing.")
    except Exception as exc:
        print(f"WARNING: Whisper alignment unavailable; using estimated caption timing. {exc}")
    return None


def make_ass_captions(script, duration, output_ass, audio_path=None):
    """Create bold karaoke captions, using Whisper word timestamps when enabled."""
    timed_words = whisper_word_timings(audio_path) if audio_path else None
    if timed_words:
        words = [item["word"] for item in timed_words]
    else:
        words = script.split()
    if not words:
        raise RuntimeError("Cannot create captions for an empty script")
    chunks = caption_chunks(words)
    weights = [max(2.0, min(10.0, len(re.sub(r"[^\w]", "", w, flags=re.UNICODE)) * 0.72)) for w in words]
    total_weight = sum(weights) or 1.0
    cursor_weight = 0.0
    cursor_word = 0
    events = []
    for chunk in chunks:
        chunk_weights = weights[cursor_word:cursor_word + len(chunk)]
        if timed_words:
            chunk_timing = timed_words[cursor_word:cursor_word + len(chunk)]
            start = max(0.0, chunk_timing[0]["start"])
            end = min(max(duration, start + 0.12), max(start + 0.12, chunk_timing[-1]["end"]))
            word_durations = [max(0.04, item["end"] - item["start"]) for item in chunk_timing]
        else:
            start = duration * cursor_weight / total_weight
            cursor_weight += sum(chunk_weights)
            end = duration * cursor_weight / total_weight
            word_durations = [max(0.04, (end - start) * w / max(0.01, sum(chunk_weights))) for w in chunk_weights]
        lines, line, line_chars = [], [], 0
        for word in chunk:
            if line and line_chars + len(word) + 1 > 19:
                lines.append(line)
                line, line_chars = [], 0
            line.append(word)
            line_chars += len(word) + (1 if len(line) > 1 else 0)
        if line:
            lines.append(line)
        lines = lines[:2]
        karaoke, wi = [], 0
        for li, line_words in enumerate(lines):
            if li:
                karaoke.append(r"\N")
            for word in line_words:
                word_cs = max(1, int(round(word_durations[wi] * 100)))
                karaoke.append(r"{\kf" + str(word_cs) + "}" + ass_escape(word))
                karaoke.append(" ")
                wi += 1
        text_line = "".join(karaoke).strip()
        events.append(
            f"Dialogue: 0,{ass_timestamp(start)},{ass_timestamp(max(start + 0.12, end))},Karaoke,,0,0,0,,{text_line}"
        )
        cursor_word += len(chunk)

    header = r"""[Script Info]
Title: Turkish Fitness Shorts Captions
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Arial,62,&H00FFFFFF,&H0000D7FF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,70,70,190,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    output_ass.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return output_ass

def clip_segment_seconds(clip_count, total_seconds=SECONDS):
    """Split the Short runtime across all downloaded clips instead of showing only clip one."""
    return max(2, (total_seconds + max(1, clip_count) - 1) // max(1, clip_count))


def make_video(clips,audio,script):
    normalized=[]
    segment_seconds = clip_segment_seconds(len(clips))
    for i,clip in enumerate(clips):
        dst=TMP/f"norm_{i}.mp4"
        # Loop very short stock footage if needed, then trim each clip to its montage segment.
        run(["ffmpeg","-y","-v","error","-stream_loop","-1","-i",str(clip),"-t",str(segment_seconds),"-vf","scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30","-an","-c:v","libx264","-preset","veryfast","-crf","23","-pix_fmt","yuv420p",str(dst)])
        normalized.append(dst)
    concat=TMP/"concat.txt"; concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in normalized),encoding="utf-8")
    montage=TMP/"montage.mp4"
    run(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i",str(concat),"-t",str(SECONDS),"-an","-c:v","libx264","-preset","veryfast","-crf","23","-pix_fmt","yuv420p",str(montage)])
    audio_len=float(run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(audio)]).stdout.strip())
    duration=min(SECONDS,max(1.0,audio_len))
    output=OUT/"fitness_shorts.mp4"
    ass=make_ass_captions(script,duration,OUT/"subtitles.ass",audio_path=audio)
    filt=str(ass.resolve()).replace("\\","/").replace(":","\\:").replace("'","\\'").replace(",","\\,")
    run(["ffmpeg","-y","-v","error","-i",str(montage),"-i",str(audio),"-vf",f"subtitles='{filt}'","-t",str(duration),"-map","0:v:0","-map","1:a:0","-shortest","-c:v","libx264","-preset","veryfast","-crf","22","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-movflags","+faststart",str(output)])
    return output

def youtube_service():
    if not TOKEN_JSON: raise RuntimeError("TOKEN_JSON secret is missing")
    creds=Credentials.from_authorized_user_info(json.loads(TOKEN_JSON),SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        else: raise RuntimeError("OAuth token invalid or missing refresh_token; re-authorize with upload and readonly scopes")
    return build("youtube","v3",credentials=creds,cache_discovery=False)

def upload(path,data,credits,thumbnail_path=None):
    if MODE!="upload": print("PREPARE MODE: video created; not uploaded."); return
    if not CONFIRM_UPLOAD: raise RuntimeError("Upload blocked: explicit CONFIRM_UPLOAD=YES approval is required for this manual run.")
    if not ALLOW_PUBLIC: raise RuntimeError("Upload blocked. After testing, set ALLOW_PUBLIC_UPLOAD=YES.")
    if not CHANNEL_ID: raise RuntimeError("YOUTUBE_CHANNEL_ID missing; upload blocked")
    yt=youtube_service(); result=yt.channels().list(part="snippet",mine=True,maxResults=50).execute(); channels=result.get("items",[])
    for ch in channels: print(f"OAuth channel: {ch['snippet']['title']} | {ch['id']}")
    target=next((c for c in channels if c["id"]==CHANNEL_ID),None)
    if not target: raise RuntimeError("Target channel ID was not visible to this OAuth account; upload blocked")
    tags=parse_list(data.get("hashtags",["#fitness","#shorts","#antrenman"]))
    desc=(str(data.get("description","Fitness önerileri"))+"\n\nBu içerik genel bilgilendirme amaçlıdır. Hareketleri kendi seviyene göre uyarla ve ağrı hissedersen dur.\n\nStock footage credits:\n"+"\n".join(credits)+"\n\n"+" ".join(tags)+" #Shorts")[:5000]
    body={"snippet":{"title":(str(data["title"])[:90]+" #Shorts")[:100],"description":desc,"tags":[t.lstrip("#") for t in tags]+["Shorts","fitness","workout"],"categoryId":"26"},"status":{"privacyStatus":"public","selfDeclaredMadeForKids":False}}
    req=yt.videos().insert(part="snippet,status",body=body,media_body=MediaFileUpload(str(path),mimetype="video/mp4",resumable=True)); response=None
    while response is None:
        status,response=req.next_chunk()
        if status: print(f"Upload: {int(status.progress()*100)}%")
    if thumbnail_path and Path(thumbnail_path).exists():
        try:
            yt.thumbnails().set(videoId=response["id"], media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")).execute()
            print("Custom thumbnail uploaded.")
        except Exception as exc:
            print(f"WARNING: Video uploaded but custom thumbnail could not be set: {exc}")
    print("Uploaded:","https://www.youtube.com/watch?v="+response["id"])

def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"): raise RuntimeError("Install FFmpeg and ensure ffmpeg/ffprobe are on PATH")
    data=topic_data(); print("Title:",data["title"]); print("Script:",data["script"])
    queries=footage_queries(data)
    print("Topic-specific footage queries:", " | ".join(queries))
    clips,credits=download_clips(queries)
    audio=asyncio.run(make_voice(data["script"]))
    video=make_video(clips,audio,data["script"])
    quality=validate_video(video, SECONDS)
    (OUT/"video_metadata.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"stock_credits.txt").write_text("\n".join(credits),encoding="utf-8")
    thumbnail=OUT/"thumbnail.jpg"
    create_thumbnail(video, data["title"], thumbnail)
    write_review_manifest(OUT, data["title"], video, thumbnail, quality, credits)
    print("Quality check:", json.dumps(quality, ensure_ascii=False))
    if not quality.get("ok"):
        raise RuntimeError("Rendered video failed quality checks; it was not uploaded. See output/review_manifest.json")
    print("Video ready for human review:",video)
    print("Thumbnail:",thumbnail)
    upload(video,data,credits,thumbnail)

if __name__=="__main__":
    try: main()
    except Exception as exc: print(f"ERROR: {exc}",file=sys.stderr); sys.exit(1)
