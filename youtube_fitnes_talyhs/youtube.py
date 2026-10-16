#!/usr/bin/env python3
"""English-language fitness YouTube Shorts automation."""
from __future__ import annotations
import asyncio, json, os, random, re, shutil, subprocess, sys, time
from pathlib import Path
import requests
import edge_tts
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
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
VOICE = os.getenv("EDGE_TTS_VOICE", "en-US-AriaNeural")
REQUESTED_TOPIC = os.getenv("FITNESS_TOPIC", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ALLOW_PUBLIC = os.getenv("ALLOW_PUBLIC_UPLOAD", "NO").upper() == "YES"

IDEAS = [
    ("3 Push-Up Mistakes to Avoid", "proper push-up form for beginners"),
    ("A Simple Warm-Up Before Every Workout", "safe beginner warm-up exercises"),
    ("How to Do Squats With Better Form", "bodyweight squat technique and safety"),
    ("Why Rest Days Help You Improve", "fitness recovery and rest days"),
    ("Build a Workout Habit That Lasts", "how to build a consistent exercise habit"),
    ("Stay Hydrated During Your Workout", "hydration reminders during exercise"),
    ("A Simple Home Workout Without Equipment", "beginner bodyweight exercises at home"),
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
        f"Today, we're focusing on {topic}.",
        "Start at a comfortable pace and choose movements you can control.",
        "Keep your posture steady, move smoothly, and breathe throughout each repetition.",
        "Before you begin, warm up with a few easy movements.",
        "If your form starts to slip, slow down or take a short break.",
        "You do not need maximum intensity to build a consistent exercise habit.",
        "Choose movements that suit your current fitness level and available space.",
        "Stop if you feel sharp pain, dizziness, or unusual discomfort.",
        "Give your body time to recover, drink water, and get enough sleep.",
        "Steady practice over time is more useful than one extremely hard workout.",
        "Focus on controlled technique instead of rushing through each repetition.",
        "Try this tip in your next session, and follow for more practical fitness advice.",
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
        "Act as an experienced American English fitness scriptwriter and meticulous copy editor. "
        "Create one original YouTube Fitness Short and return ONLY valid JSON with these keys: "
        "title, topic, script, search_terms (array of 3-5 strings), description, hashtags (array). "
        f"Subject: {topic}. Runtime: {SECONDS} seconds. The spoken script MUST contain {min_words}-{max_words} words "
        f"(aim for about {target_words}); this limit is important because the voice-over must fit the video. "
        "Write fluent, natural, idiomatic US English with correct grammar, spelling, punctuation, and clear pronunciation. "
        "Read the script aloud mentally and rewrite any stiff, translated-sounding, repetitive, or awkward sentence. "
        "Use contractions where natural, varied sentence openings, short speakable sentences, and a compelling hook in the first line. "
        "Structure: hook, one clear practical tip, a brief actionable explanation, sensible safety note when relevant, and a natural CTA. "
        "The script must contain ONLY words the narrator should speak: no headings, stage directions, emojis, or bullet points. "
        "Make every tip specific to the subject; never invent statistics, promise results, shame bodies, or give medical advice. "
        "Keep claims realistic and beginner-friendly. The title must be concise, accurate, and clickable without clickbait. "
        "The description should be natural English and summarize the actual video. "
        "Search terms must describe relevant real footage for this exact subject, not generic unrelated gym clips. "
        "Return clean JSON only; do not include markdown fences or commentary."
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
                "Rewrite this fitness Short script in polished, natural American English. "
                f"The final spoken script must contain {min_words}-{max_words} words, with no headings or stage directions. "
                "Preserve accurate, safe advice and the same topic. Return the same JSON keys only. "
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
        data["description"] = str(data.get("description") or "Beginner-friendly fitness tips.").strip()
        if not isinstance(data.get("search_terms"), list):
            data["search_terms"] = [str(data["search_terms"])]
        data["search_terms"] = [str(x).strip() for x in data["search_terms"] if str(x).strip()][:5]
        if not data["search_terms"]:
            data["search_terms"] = [f"{topic} exercise demonstration"]
        if not isinstance(data.get("hashtags"), list):
            data["hashtags"] = ["#fitness", "#shorts", "#workout"]
        data["hashtags"] = [str(x).strip() for x in data["hashtags"] if str(x).strip()][:8]
        if not data["hashtags"]:
            data["hashtags"] = ["#fitness", "#shorts", "#workout"]
        print(f"English script quality gate: {script_word_count(data['script'])} words; target {min_words}-{max_words}.")
        return data

    print("WARNING: AI script was unavailable or failed the duration/quality checks; using the reviewed English fallback.")
    return {
        "title": title, "topic": topic,
        "script": fallback_script(topic),
        "search_terms": [f"{topic} exercise demonstration", f"{topic} proper technique", "beginner fitness exercise form"],
        "description": f"Practical, beginner-friendly advice about {topic}. Choose movements that suit your ability and stop if you feel pain.",
        "hashtags": ["#fitness", "#shorts", "#workout", "#exercise"]
    }

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

def download_clips(terms):
    all_clips=[]
    for q in parse_list(terms)[:4]:
        for fn in (pexels,pixabay):
            try: all_clips.extend(fn(q))
            except Exception as e: print(f"WARNING: stock search error for {q}: {e}")
    # Keep provider relevance order instead of randomizing clips. A topic-specific query should not be diluted by generic gym footage.
    used=set(); paths=[]; credits=[]
    for clip in all_clips:
        if clip["url"] in used: continue
        tags = " ".join(clip.get("tags", [])).lower()
        query_words = {w for w in re.findall(r"[a-z0-9]+", clip.get("query", "").lower()) if len(w) > 2}
        tag_words = {w for w in re.findall(r"[a-z0-9]+", tags) if len(w) > 2}
        if tag_words and query_words and not (query_words & tag_words):
            # Pixabay supplies tags; reject clear mismatches. Pexels does not expose equivalent tags in this endpoint.
            continue
        used.add(clip["url"]); path=TMP/f"clip_{len(paths)+1}.mp4"
        try:
            with requests.get(clip["url"],stream=True,timeout=90) as r:
                r.raise_for_status()
                with path.open("wb") as f:
                    for chunk in r.iter_content(512*1024):
                        if chunk: f.write(chunk)
            run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)])
            paths.append(path); credits.append(f"- {clip['credit']}: {clip['page']}")
            if len(paths)>=5: break
        except Exception as e:
            path.unlink(missing_ok=True); print(f"WARNING: skipping invalid stock clip: {e}")
    if not paths: raise RuntimeError("No stock clips downloaded. Add PEXELS_API_KEY and/or PIXABAY_API_KEY as secrets.")
    return paths,credits

async def make_voice(script):
    path=TMP/"voice.mp3"
    await edge_tts.Communicate(script,VOICE,rate="+0%").save(str(path))
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
    weights = [max(2.0, min(10.0, len(re.sub(r"[^A-Za-z0-9]", "", w)) * 0.72)) for w in words]
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
Title: English Fitness Shorts Captions
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

def make_video(clips,audio,script):
    normalized=[]
    for i,clip in enumerate(clips):
        dst=TMP/f"norm_{i}.mp4"
        run(["ffmpeg","-y","-v","error","-i",str(clip),"-t",str(SECONDS),"-vf","scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30","-an","-c:v","libx264","-preset","veryfast","-crf","23","-pix_fmt","yuv420p",str(dst)])
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
    if not ALLOW_PUBLIC: raise RuntimeError("Upload blocked. After testing, set ALLOW_PUBLIC_UPLOAD=YES.")
    if not CHANNEL_ID: raise RuntimeError("YOUTUBE_CHANNEL_ID missing; upload blocked")
    yt=youtube_service(); result=yt.channels().list(part="snippet",mine=True,maxResults=50).execute(); channels=result.get("items",[])
    for ch in channels: print(f"OAuth channel: {ch['snippet']['title']} | {ch['id']}")
    target=next((c for c in channels if c["id"]==CHANNEL_ID),None)
    if not target: raise RuntimeError("Target channel ID was not visible to this OAuth account; upload blocked")
    tags=parse_list(data.get("hashtags",["#fitness","#shorts","#workout"]))
    desc=(str(data.get("description","Fitness tips"))+"\n\nGeneral information only. Adapt exercises to your ability and stop if you feel pain.\n\nStock footage credits:\n"+"\n".join(credits)+"\n\n"+" ".join(tags)+" #Shorts")[:5000]
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
    clips,credits=download_clips(data.get("search_terms",["fitness workout gym"]))
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
