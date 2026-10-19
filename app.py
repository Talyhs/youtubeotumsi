from __future__ import annotations
import hashlib, io, json, os, sqlite3, zipfile
from datetime import date, datetime, timezone
from pathlib import Path
import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(page_title="Talyhs YouTube Studio", page_icon="🎬", layout="wide")
API="https://api.github.com"
REPO=os.getenv("GITHUB_REPOSITORY","Talyhs/youtubeotumsi").strip()
WORKFLOW=os.getenv("GITHUB_WORKFLOW_FILE","main.yml").strip()
BRANCH=os.getenv("GITHUB_BRANCH","main").strip()
GH_TOKEN=os.getenv("GH_TOKEN","").strip()
PASSWORD=os.getenv("DASHBOARD_PASSWORD","").strip()
DB=Path(os.getenv("STUDIO_DB_PATH","studio_calendar.sqlite3"))
HEADERS={"Accept":"application/vnd.github+json","Authorization":f"Bearer {GH_TOKEN}","X-GitHub-Api-Version":"2022-11-28","User-Agent":"Talyhs-YouTube-Studio"}
LANG={"Azərbaycan dili":"az","English":"en","Türkçe":"tr"}
DUR={"30 saniyə":"30","45 saniyə":"45","50 saniyə":"50","55 saniyə":"55","1 dəqiqə":"60","3 dəqiqə":"180","5 dəqiqə":"300","10 dəqiqə":"600","10 dəqiqə 1 saniyə":"601"}

st.markdown("""<style>
.stApp{background:radial-gradient(ellipse at 10% 0%,#17213b 0%,#0b1020 45%,#080b14 100%);color:#eef2ff}
[data-testid="stSidebar"]{background:#0c1222;border-right:1px solid #25314b}
.block-container{padding-top:1.5rem;max-width:1500px}
div[data-testid="stMetric"]{background:#121b2e;border:1px solid #273551;padding:15px;border-radius:14px}
div[data-testid="stForm"]{background:#10182a;border:1px solid #26334d;padding:16px;border-radius:14px}
.stButton>button[kind="primary"]{background:#6d5dfc;border:0;color:white;border-radius:10px;font-weight:700}
hr{border-color:#26334d}
</style>""",unsafe_allow_html=True)

def gh(method,path,params=None,payload=None,timeout=30):
    if not GH_TOKEN: raise RuntimeError("Hosting mühitində GH_TOKEN təyin edilməyib.")
    r=requests.request(method,f"{API}/repos/{REPO}/{path}",headers=HEADERS,params=params,json=payload,timeout=timeout)
    if r.status_code>=400: raise RuntimeError(f"GitHub API {r.status_code}: {r.text[:600]}")
    return r.json() if r.text.strip() else None

def dispatch(inputs, workflow=None):
    selected_workflow = workflow or ACTIVE_WORKFLOW
    gh("POST",f"actions/workflows/{selected_workflow}/dispatches",payload={"ref":BRANCH,"inputs":inputs})

def init_db():
    DB.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(DB) as d:
        d.execute("""CREATE TABLE IF NOT EXISTS calendar(id INTEGER PRIMARY KEY,topic TEXT,language TEXT,planned_date TEXT,planned_time TEXT,video_format TEXT,duration TEXT,status TEXT,notes TEXT,created_at TEXT)""")

def rows():
    init_db()
    with sqlite3.connect(DB) as d:
        d.row_factory=sqlite3.Row
        return [dict(x) for x in d.execute("SELECT * FROM calendar ORDER BY planned_date,planned_time,id DESC")]

def add_calendar(topic,lang,day,hour,fmt,duration,notes):
    init_db()
    with sqlite3.connect(DB) as d:
        d.execute("INSERT INTO calendar(topic,language,planned_date,planned_time,video_format,duration,status,notes,created_at) VALUES(?,?,?,?,?,?,'planned',?,?)",
                  (topic,lang,day,hour,fmt,duration,notes,datetime.now(timezone.utc).isoformat()))

def gate():
    if not PASSWORD:
        st.error("Təhlükəsizlik üçün DASHBOARD_PASSWORD təyin edilməyib. Panel bağlıdır."); st.stop()
    if "studio_auth" not in st.session_state: st.session_state.studio_auth=False
    if not st.session_state.studio_auth:
        st.markdown("# 🎬 Talyhs YouTube Studio")
        st.caption("Creator command center · video production · analytics")
        with st.form("login"):
            p=st.text_input("Panel şifrəsi",type="password")
            ok=st.form_submit_button("Daxil ol",use_container_width=True)
        if ok:
            if hashlib.sha256(p.encode()).digest()==hashlib.sha256(PASSWORD.encode()).digest():
                st.session_state.studio_auth=True; st.rerun()
            st.error("Şifrə düzgün deyil.")
        st.stop()

def runs(n=15, workflow=None):
    selected_workflow = workflow or ACTIVE_WORKFLOW
    return gh("GET",f"actions/workflows/{selected_workflow}/runs",params={"per_page":n}).get("workflow_runs",[])

def status(r):
    if r.get("status")=="in_progress": return "🟡 İcra olunur"
    if r.get("status") in ("queued","waiting","requested"): return "⏳ Növbədə"
    return {"success":"✅ Uğurlu","failure":"❌ Xəta","cancelled":"⏹ Dayandırılıb"}.get(r.get("conclusion"),r.get("conclusion") or r.get("status") or "Naməlum")

def youtube_stats():
    if ACTIVE_CHANNEL["kind"] == "fitness":
        token=os.getenv("FITNESS_YOUTUBE_TOKEN_JSON","").strip() or os.getenv("FITNESS_TOKEN_JSON","").strip()
    else:
        token=os.getenv("YOUTUBE_TOKEN_JSON","").strip() or os.getenv("TOKEN_JSON","").strip()
    if not token: raise RuntimeError("YOUTUBE_TOKEN_JSON təyin edilməyib.")
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    info=json.loads(token)
    cred=Credentials.from_authorized_user_info(info,scopes=["https://www.googleapis.com/auth/youtube.readonly"])
    api=build("youtube","v3",credentials=cred,cache_discovery=False)
    res=api.channels().list(part="snippet,statistics",mine=True).execute()
    if not res.get("items"): raise RuntimeError("OAuth hesabında kanal tapılmadı.")
    ch=res["items"][0]; s=ch.get("statistics",{})
    summary={"Kanal":ch["snippet"]["title"],"Baxışlar":int(s.get("viewCount",0)),"Abunəçilər":int(s.get("subscriberCount",0)),"Videolar":int(s.get("videoCount",0)),"Kanal ID":ch["id"]}
    sr=api.search().list(part="snippet",forMine=True,type="video",order="date",maxResults=10).execute()
    ids=[x.get("id",{}).get("videoId") for x in sr.get("items",[]) if x.get("id",{}).get("videoId")]
    vids=[]
    if ids:
        for v in api.videos().list(part="snippet,statistics",id=",".join(ids)).execute().get("items",[]):
            stt=v.get("statistics",{})
            vids.append({"Başlıq":v["snippet"]["title"],"ID":v["id"],"Baxış":int(stt.get("viewCount",0)),"Bəyənmə":int(stt.get("likeCount",0))})
    return summary,vids

def thumbnail(title,bg=None):
    W,H=1280,720
    if bg:
        im=Image.open(bg).convert("RGB"); scale=max(W/im.width,H/im.height); im=im.resize((int(im.width*scale),int(im.height*scale)))
        x=(im.width-W)//2;y=(im.height-H)//2;im=im.crop((x,y,x+W,y+H))
    else:
        im=Image.new("RGB",(W,H),(12,20,42)); d=ImageDraw.Draw(im)
        for x in range(W):
            for y in range(H):
                g=max(0,1-(((x-1050)/600)**2+((y-270)/450)**2)**.5)
                im.putpixel((x,y),(int(10+g*35),int(20+g*70),int(45+g*125)))
    shade=Image.new("RGBA",(W,H),(0,0,0,0)); ImageDraw.Draw(shade).rectangle((0,0,850,H),fill=(3,7,18,155))
    im=Image.alpha_composite(im.convert("RGBA"),shade); d=ImageDraw.Draw(im)
    try: font=ImageFont.truetype("DejaVuSans-Bold.ttf",68)
    except OSError:
        try: font=ImageFont.truetype("arialbd.ttf",68)
        except OSError: font=ImageFont.load_default()
    lines=[];line=""
    for word in title[:85].split():
        test=(line+" "+word).strip()
        if d.textbbox((0,0),test,font=font)[2]>740 and line: lines.append(line);line=word
        else: line=test
    if line: lines.append(line)
    y=max(65,(H-min(len(lines),4)*88)//2)
    for t in lines[:4]:
        d.text((65,y+4),t,font=font,fill=(0,0,0,255),stroke_width=2,stroke_fill=(0,0,0,255))
        d.text((61,y),t,font=font,fill=(255,255,255,255),stroke_width=1,stroke_fill=(15,25,45,255));y+=88
    d.rounded_rectangle((64,625,390,675),radius=12,fill=(108,93,252,255));d.text((84,638),"TALYHS STUDIO",fill="white")
    out=io.BytesIO();im.convert("RGB").save(out,format="JPEG",quality=92);out.seek(0);return out

gate();init_db()
CHANNELS = {
    "Əsas YouTube kanalı": {"kind":"main", "workflow":WORKFLOW, "channel_id":os.getenv("YOUTUBE_CHANNEL_ID","").strip()},
    "Fitness Shorts · English": {"kind":"fitness", "workflow":"fitness-shorts.yml", "channel_id":os.getenv("FITNESS_YOUTUBE_CHANNEL_ID","UC7_pFbnnuMWT_US47_FD6MDA").strip()},
}
st.sidebar.markdown("## 🎬 TALYHS STUDIO")
st.sidebar.caption("Creator command center")
active_name=st.sidebar.selectbox("İdarə edilən kanal",list(CHANNELS),key="active_channel")
ACTIVE_CHANNEL=CHANNELS[active_name]
ACTIVE_WORKFLOW=ACTIVE_CHANNEL["workflow"]
st.sidebar.caption("Kanal ID: "+(ACTIVE_CHANNEL["channel_id"] or "GitHub dəyişənindən götürüləcək"))
page=st.sidebar.radio("Naviqasiya",["İdarə paneli","Video istehsalı","Montaj və səs","Thumbnail laboratoriyası","Yayım təqvimi","İcra tarixçəsi və loglar","YouTube analitikası","Quraşdırma"])
if st.sidebar.button("Çıxış"): st.session_state.studio_auth=False;st.rerun()
st.sidebar.divider();st.sidebar.caption(f"{REPO} · workflow: {ACTIVE_WORKFLOW}")
st.title("Talyhs YouTube Studio")
st.caption("English Fitness Shorts Bot" if ACTIVE_CHANNEL["kind"] == "fitness" else "Peşəkar qaranlıq studiya · istehsal · montaj · yayım")
if ACTIVE_CHANNEL["kind"] == "fitness":
    st.info("Fitness rejimi: ingilis dilində Shorts · Edge TTS neural səs · Pexels/Pixabay görüntüləri · subtitrlər · 30/45/60 saniyə. İlk olaraq Prepare seç və videonu yoxla.")
if not GH_TOKEN: st.warning("GH_TOKEN yoxdur. GitHub əmrləri üçün Render mühitinə token əlavə et.")

if page=="İdarə paneli":
    a,b,c=st.columns(3)
    try:
        rr=runs(15);a.metric("Son icralar",len(rr));b.metric("İcra olunur",sum(x.get("status")=="in_progress" for x in rr));c.metric("Xətalar",sum(x.get("conclusion")=="failure" for x in rr))
        st.subheader("Son tapşırıqlar")
        for r in rr[:6]:
            with st.container(border=True):
                x,y=st.columns([4,1]);x.markdown(f"**{r.get('display_title') or r.get('name') or 'Video işi'}**");x.caption(f"#{r.get('run_number')} · {r.get('created_at','').replace('T',' ').replace('Z',' UTC')}");x.write(status(r));y.link_button("GitHub logları",r.get("html_url",f"https://github.com/{REPO}/actions"))
    except Exception as e: st.info("GitHub statusu oxunmadı: "+str(e))
    if st.button("💪 English Fitness Short hazırla" if ACTIVE_CHANNEL["kind"] == "fitness" else "🧠 Azərbaycan dilində 50 saniyəlik Shorts hazırla",type="primary"):
        try:
            if ACTIVE_CHANNEL["kind"] == "fitness":
                dispatch({"mode":"prepare","topic":"Beginner home workout tips","duration":"45","voice":"female"},workflow=ACTIVE_WORKFLOW)
            else:
                dispatch({"topic":"İnsan beyni haqqında maraqlı faktlar","language":"az","duration":"50","video_format":"vertical","voice":"female","voice_provider":"edge","stock_sources":"Pixabay,Pexels","subtitles":"true","thumbnail":"true","seo":"true","privacy":"private","publish":"prepare"})
            st.success("Əmr göndərildi. Hazırlıq rejimi seçilib.")
        except Exception as e: st.error(str(e))

elif page=="Video istehsalı":
    st.subheader("Yeni video")
    with st.form("create"):
        if ACTIVE_CHANNEL["kind"] == "fitness":
            fitness_topics = ["Beginner Home Workout", "Fat Loss Workout", "Muscle Building Tips", "Core & Abs Workout", "Leg Day Exercises", "Upper Body Workout", "Warm-Up & Mobility", "Healthy Nutrition Tips", "Common Gym Mistakes", "Recovery & Rest Days", "Custom topic…"]
            selected_fitness_topic = st.selectbox("Fitness mövzusu (English)", fitness_topics)
            custom_fitness_topic = st.text_input("Öz mövzun (istəyə görə)", placeholder="e.g. 3 beginner mistakes in push-ups") if selected_fitness_topic == "Custom topic…" else ""
            topic = custom_fitness_topic.strip() if selected_fitness_topic == "Custom topic…" else selected_fitness_topic
        else:
            topic_options=["Telefon Nasıl İcat Edildi?","Firavunlar: Antik Mısır'ın Gizemleri","İnsan Beyni Hakkında İlginç Gerçekler","Özel konu yaz…"]
            selected_topic=st.selectbox("Hazır mövzu",topic_options,index=0)
            custom_topic=st.text_input("Öz mövzun",placeholder="Türk dilində mövzu daxil et") if selected_topic=="Özel konu yaz…" else ""
            topic=custom_topic.strip() if selected_topic=="Özel konu yaz…" else selected_topic
        a,b,c=st.columns(3)
        if ACTIVE_CHANNEL["kind"] == "fitness":
            lang=a.selectbox("Dil",["English"],0);dur=b.selectbox("Müddət",["30 saniyə","45 saniyə","1 dəqiqə"],1);fmt=c.selectbox("Format",["Shorts · 9:16"])
        else:
            lang=a.selectbox("Dil",list(LANG),2);dur=b.selectbox("Müddət",list(DUR),1);fmt=c.selectbox("Format",["Shorts · 9:16","Standart · 16:9"])
        if ACTIVE_CHANNEL["kind"] == "fitness":
            a,b=st.columns(2)
            voice_options = ["female","male","auto"]
            voice=a.selectbox("English neural voice",voice_options,0)
            voice_provider="edge"
            stock=b.multiselect("Stok mənbələri",["Pixabay","Pexels"],["Pixabay","Pexels"])
            st.caption("Female: en-US-AriaNeural · Male: en-US-GuyNeural · səs mühərriki: Edge TTS.")
        else:
            a,b,c=st.columns(3)
            voice=a.selectbox("Səs",["male","female","auto"],0)
            provider_options=["edge","ema","kokoro","elevenlabs","fliki","auto"]
            provider_default={"az":"edge","tr":"ema","en":"kokoro"}.get(LANG[lang],"edge")
            voice_provider=b.selectbox("AI səs mühərriki",provider_options,index=provider_options.index(provider_default))
            stock=c.multiselect("Stok mənbələri",["Pixabay","Pexels"],["Pixabay","Pexels"])
            st.caption("Tövsiyə: Azərbaycan dili — Edge; Türk dili — EMA; İngilis dili — Kokoro. API tələb edən xidmətlər üçün uyğun GitHub Secret lazımdır.")
        a,b,c=st.columns(3);subs=a.checkbox("Subtitrlər",True);thumb=b.checkbox("Thumbnail",True);seo=c.checkbox("SEO metadata",True)
        privacy=st.selectbox("Görünmə",["private","unlisted","public"],0);publish=st.radio("Əməl",["Yalnız hazırla","Hazırla və YouTube-a yüklə"],0);confirm=st.checkbox("İctimai yayımı təsdiqləyirəm. Fitness kanalının upload rejimi hazırda videonu PUBLIC yayımlayır.")
        ok=st.form_submit_button("🚀 İstehsalı başlat",type="primary",use_container_width=True)
    if ok:
        if not topic.strip(): st.error("Mövzunu daxil et.")
        elif publish!="Yalnız hazırla" and (privacy=="public" or ACTIVE_CHANNEL["kind"]=="fitness") and not confirm: st.error("İctimai yayım üçün təsdiq tələb olunur. Fitness workflow hazırda yalnız public upload edir.")
        else:
            try:
                if ACTIVE_CHANNEL["kind"] == "fitness":
                    secs = "30" if int(DUR[dur]) <= 30 else ("60" if int(DUR[dur]) >= 60 else "45")
                    dispatch({"mode":"upload" if publish!="Yalnız hazırla" else "prepare","topic":topic.strip()[:180],"duration":secs,"voice":voice},workflow=ACTIVE_WORKFLOW)
                else:
                    dispatch({"topic":topic.strip()[:180],"language":LANG[lang],"duration":DUR[dur],"video_format":"vertical" if fmt.startswith("Shorts") else "horizontal","voice":voice,"voice_provider":voice_provider,"stock_sources":",".join(stock) or "Pixabay","subtitles":str(subs).lower(),"thumbnail":str(thumb).lower(),"seo":str(seo).lower(),"privacy":privacy,"publish":"upload" if publish!="Yalnız hazırla" else "prepare"},workflow=ACTIVE_WORKFLOW)
                st.success("Əmr GitHub Actions-a göndərildi.")
            except Exception as e: st.error(str(e))

elif page=="Montaj və səs":
    st.subheader("Montaj və səs parametrləri")
    st.info("Buradan göndərilən parametrlər mövcud GitHub workflow input-larına ötürülür. Əlavə lokal audio mastering Windows masaüstü tətbiqindədir.")
    with st.form("media"):
        topic=st.text_input("Mövzu","İnsan beyni haqqında maraqlı faktlar");lang=st.selectbox("Dil",list(LANG),0);dur=st.selectbox("Müddət",list(DUR),1);voice=st.selectbox("Səs",["male","female","auto"],0);fmt=st.selectbox("Format",["vertical","horizontal"]);subs=st.checkbox("Subtitrlər",True);stock=st.multiselect("Stok mənbələri",["Pixabay","Pexels"],["Pixabay","Pexels"]);ok=st.form_submit_button("Parametrlərlə hazırla",type="primary")
    if ok:
        try:
            if ACTIVE_CHANNEL["kind"] == "fitness":
                secs = "30" if int(DUR[dur]) <= 30 else ("60" if int(DUR[dur]) >= 60 else "45")
                dispatch({"mode":"prepare","topic":topic,"duration":secs,"voice":voice},workflow=ACTIVE_WORKFLOW)
            else:
                dispatch({"topic":topic,"language":LANG[lang],"duration":DUR[dur],"voice":voice,"video_format":fmt,"subtitles":str(subs).lower(),"stock_sources":",".join(stock) or "Pixabay","thumbnail":"true","seo":"true","privacy":"private","publish":"prepare"},workflow=ACTIVE_WORKFLOW)
            st.success("Tapşırıq göndərildi.")
        except Exception as e: st.error(str(e))

elif page=="Thumbnail laboratoriyası":
    title=st.text_input("Thumbnail başlığı","İnsan beyninin 5 sirri");bg=st.file_uploader("Arxa fon (istəyə görə)",type=["png","jpg","jpeg","webp"])
    if st.button("Thumbnail yarat",type="primary"):
        try: st.session_state.thumb=thumbnail(title,bg).getvalue();st.success("1280 × 720 thumbnail hazırdır.")
        except Exception as e: st.error(str(e))
    if st.session_state.get("thumb"):
        st.image(st.session_state.thumb,use_container_width=True);st.download_button("JPG yüklə",st.session_state.thumb,"talyhs_thumbnail.jpg","image/jpeg")

elif page=="Yayım təqvimi":
    with st.form("calendar"):
        topic=st.text_input("Mövzu");a,b,c=st.columns(3);lang=a.selectbox("Dil",list(LANG),0);day=b.date_input("Tarix",date.today());hour=c.time_input("Saat");fmt=st.selectbox("Format",["vertical","horizontal"]);dur=st.selectbox("Müddət",list(DUR),1);notes=st.text_area("Qeydlər");save=st.form_submit_button("Təqvimə əlavə et")
    if save:
        if not topic.strip(): st.error("Mövzunu daxil et.")
        else: add_calendar(topic.strip(),LANG[lang],day.isoformat(),hour.strftime("%H:%M"),fmt,DUR[dur],notes);st.success("Təqvimə əlavə edildi.");st.rerun()
    items=rows()
    if items:
        st.dataframe(items,use_container_width=True,hide_index=True)
        choices={f"#{x['id']} · {x['planned_date']} {x['planned_time']} · {x['topic']}":x for x in items};pick=st.selectbox("İndi göndər",list(choices))
        if st.button("Seçilmiş tapşırığı indi göndər",type="primary"):
            x=choices[pick]
            try:
                if ACTIVE_CHANNEL["kind"] == "fitness":
                    secs = "30" if int(x["duration"]) <= 30 else ("60" if int(x["duration"]) >= 60 else "45")
                    dispatch({"mode":"prepare","topic":x["topic"],"duration":secs,"voice":"female"},workflow=ACTIVE_WORKFLOW)
                else:
                    dispatch({"topic":x["topic"],"language":x["language"],"duration":x["duration"],"video_format":x["video_format"],"voice":"male","stock_sources":"Pixabay,Pexels","subtitles":"true","thumbnail":"true","seo":"true","privacy":"private","publish":"prepare"},workflow=ACTIVE_WORKFLOW)
                with sqlite3.connect(DB) as d:d.execute("UPDATE calendar SET status='dispatched' WHERE id=?",(x["id"],))
                st.success("Tapşırıq göndərildi.");st.rerun()
            except Exception as e:st.error(str(e))
    else: st.info("Təqvim boşdur.")
    st.caption("Təqvim hazırda planlaşdırma və əl ilə başlatma üçündür; seçilən saatda avtomatik icra etmir.")

elif page=="İcra tarixçəsi və loglar":
    n=st.slider("İcra sayı",5,30,15)
    try:
        for r in runs(n):
            with st.container(border=True):
                a,b,c=st.columns([4,1,1]);a.markdown(f"**{r.get('display_title') or r.get('name') or 'Video işi'}**");a.caption(f"#{r.get('run_number')} · {r.get('created_at','')}");a.write(status(r));b.link_button("GitHub",r.get("html_url",f"https://github.com/{REPO}/actions"))
                if r.get("status")=="completed" and c.button("Logları oxu",key=f"logbtn{r['id']}"):
                    resp=requests.get(f"{API}/repos/{REPO}/actions/runs/{r['id']}/logs",headers=HEADERS,timeout=60);resp.raise_for_status()
                    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                        names=z.namelist()
                        if names:
                            text=z.read(names[0]).decode("utf-8",errors="replace")[-25000:];st.text_area(f"Log #{r['run_number']}",text,height=300,key=f"logtext{r['id']}")
                            st.download_button("Log faylını yüklə",text,f"run_{r['id']}.log",key=f"logdl{r['id']}")
    except Exception as e:st.error("Loglar oxunmadı: "+str(e))

elif page=="YouTube analitikası":
    st.caption("OAuth tokenində youtube.readonly scope olmalıdır; yalnız upload scope statistikaya kifayət etməyə bilər.")
    if st.button("Statistikanı yüklə",type="primary"):
        try: st.session_state.yt_summary,st.session_state.yt_videos=youtube_stats()
        except Exception as e:st.error(str(e))
    if st.session_state.get("yt_summary"):
        s=st.session_state.yt_summary;st.subheader(s["Kanal"]);a,b,c=st.columns(3);a.metric("Baxışlar",f"{s['Baxışlar']:,}");b.metric("Abunəçilər",f"{s['Abunəçilər']:,}");c.metric("Videolar",f"{s['Videolar']:,}");st.caption("Kanal ID: "+s["Kanal ID"]);st.dataframe(st.session_state.yt_videos,use_container_width=True,hide_index=True)

else:
    st.subheader("Quraşdırma və təhlükəsizlik")
    st.write({"Repository":REPO,"Workflow":WORKFLOW,"Branch":BRANCH,"GitHub token":"quraşdırılıb" if GH_TOKEN else "çatışmır","Panel şifrəsi":"quraşdırılıb" if PASSWORD else "çatışmır"})
    st.markdown("Hostingdə DASHBOARD_PASSWORD, GH_TOKEN, GITHUB_REPOSITORY, GITHUB_WORKFLOW_FILE və GITHUB_BRANCH təyin et. Əsas kanal üçün YOUTUBE_TOKEN_JSON, fitness kanalının analitikası üçün FITNESS_YOUTUBE_TOKEN_JSON və FITNESS_YOUTUBE_CHANNEL_ID əlavə et. Token və API açarlarını koda və brauzerə yazma. GitHub tokeninə yalnız lazım olan repository və Actions icazələrini ver.")
    st.link_button("Repository",f"https://github.com/{REPO}");st.link_button("GitHub Actions",f"https://github.com/{REPO}/actions")
