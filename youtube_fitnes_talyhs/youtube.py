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

def topic_data():
    title, topic = IDEAS[int(time.time() // 14400) % len(IDEAS)]
    if REQUESTED_TOPIC:
        title = REQUESTED_TOPIC[:90]
        topic = REQUESTED_TOPIC[:180]
    data = gen_json(
        "Write an original English YouTube Fitness Shorts script. Return valid JSON with keys "
        "title, topic, script, search_terms (array), description, hashtags (array). "
        f"Topic: {topic}. Duration: {SECONDS} seconds. Natural spoken American English, a strong hook in the first 2 seconds, "
        "short sentences, safe general fitness education, and a brief call to action. No medical claims, "
        "guaranteed results, or dangerous advice. Write about 90–120 English words."
    )
    if data and all(k in data for k in ("title", "script", "search_terms")):
        data.setdefault("topic", topic); data.setdefault("description", "Beginner-friendly general fitness tips.")
        data.setdefault("hashtags", ["#fitness", "#shorts", "#workout"])
        return data
    return {
        "title": title, "topic": topic,
        "script": f"Today's fitness focus is {topic}. Start with a comfortable pace and choose movements that match your current ability. Warm up with a few easy movements before training, keep your technique controlled, and breathe naturally. If an exercise feels too difficult, choose an easier variation rather than forcing it. Stop if you feel sharp pain. Consistency matters more than trying to do everything in one day. Save this video and take one positive step for your fitness today!",
        "search_terms": ["fitness workout gym exercise", "person exercising at home"],
        "description": "Beginner-friendly fitness tips. Adapt exercises to your ability and stop if you feel pain.",
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
            out.append({"url":files[0]["link"],"credit":f"Pexels video by {v.get('user',{}).get('name','creator')}","page":v.get("url","")})
    return out

def pixabay(q):
    if not PIXABAY_API_KEY: return []
    r=requests.get("https://pixabay.com/api/videos/",params={"key":PIXABAY_API_KEY,"q":q,"per_page":10,"safesearch":"true"},timeout=30); r.raise_for_status()
    out=[]
    for v in r.json().get("hits",[]):
        variants=v.get("videos",{}); f=variants.get("medium") or variants.get("small") or variants.get("large")
        if f and f.get("url"): out.append({"url":f["url"],"credit":f"Pixabay video by {v.get('user','creator')}","page":v.get("pageURL","")})
    return out

def download_clips(terms):
    all_clips=[]
    for q in parse_list(terms)[:4]:
        for fn in (pexels,pixabay):
            try: all_clips.extend(fn(q))
            except Exception as e: print(f"WARNING: stock search error for {q}: {e}")
    random.shuffle(all_clips); used=set(); paths=[]; credits=[]
    for clip in all_clips:
        if clip["url"] in used: continue
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

def make_video(clips,audio,script):
    normalized=[]
    for i,clip in enumerate(clips):
        dst=TMP/f"norm_{i}.mp4"
        run(["ffmpeg","-y","-v","error","-i",str(clip),"-t",str(SECONDS),"-vf","scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30","-an","-c:v","libx264","-preset","veryfast","-crf","23","-pix_fmt","yuv420p",str(dst)])
        normalized.append(dst)
    concat=TMP/"concat.txt"; concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in normalized),encoding="utf-8")
    montage=TMP/"montage.mp4"
    run(["ffmpeg","-y","-v","error","-f","concat","-safe","0","-i",str(concat),"-t",str(SECONDS),"-an","-c:v","libx264","-preset","veryfast","-crf","23","-pix_fmt","yuv420p",str(montage)])
    words=script.split(); size=max(4,min(8,len(words)//max(1,SECONDS//3))); chunks=[" ".join(words[i:i+size]) for i in range(0,len(words),size)]
    srt=TMP/"subtitles.srt"; each=SECONDS/max(1,len(chunks)); lines=[]
    for i,chunk in enumerate(chunks): lines += [str(i+1),f"{timestamp(i*each)} --> {timestamp(min(SECONDS,(i+1)*each))}",chunk,""]
    srt.write_text("\n".join(lines),encoding="utf-8")
    filt=str(srt.resolve()).replace("\\","/").replace(":",r"\:").replace("'",r"\'").replace(",",r"\,")
    audio_len=float(run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(audio)]).stdout.strip())
    duration=min(SECONDS,max(30,int(audio_len+1))); output=OUT/"fitness_shorts.mp4"
    run(["ffmpeg","-y","-v","error","-i",str(montage),"-i",str(audio),"-vf",f"subtitles='{filt}':force_style='FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=150'","-t",str(duration),"-map","0:v:0","-map","1:a:0","-shortest","-c:v","libx264","-preset","veryfast","-crf","22","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-movflags","+faststart",str(output)])
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

def upload(path,data,credits):
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
    print("Uploaded:","https://www.youtube.com/watch?v="+response["id"])

def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"): raise RuntimeError("Install FFmpeg and ensure ffmpeg/ffprobe are on PATH")
    data=topic_data(); print("Title:",data["title"]); print("Script:",data["script"])
    clips,credits=download_clips(data.get("search_terms",["fitness workout gym"]))
    audio=asyncio.run(make_voice(data["script"]))
    video=make_video(clips,audio,data["script"])
    (OUT/"video_metadata.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"stock_credits.txt").write_text("\n".join(credits),encoding="utf-8")
    print("Video ready:",video); upload(video,data,credits)

if __name__=="__main__":
    try: main()
    except Exception as exc: print(f"ERROR: {exc}",file=sys.stderr); sys.exit(1)
