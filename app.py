import os
import time
from datetime import datetime, timezone

import requests
import streamlit as st

st.set_page_config(page_title="Talyhs Studio", page_icon="🎬", layout="wide")

REPO = os.getenv("GITHUB_REPOSITORY", "Talyhs/youtubeotumsi").strip()
WORKFLOW = os.getenv("GITHUB_WORKFLOW_FILE", "main.yml").strip()
GH_TOKEN = os.getenv("GH_TOKEN", "").strip()
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "").strip()
API = "https://api.github.com"
HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GH_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
}

if not DASHBOARD_PASSWORD:
    st.error("DASHBOARD_PASSWORD konfiqurasiya edilməyib. Panel təhlükəsizlik üçün bağlıdır.")
    st.stop()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🎬 Talyhs Studio")
    st.caption("YouTube video istehsal paneli")
    with st.form("login"):
        password = st.text_input("Panel şifrəsi", type="password")
        submitted = st.form_submit_button("Daxil ol", use_container_width=True)
    if submitted:
        if password and password == DASHBOARD_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        st.error("Şifrə düzgün deyil.")
    st.stop()

if not GH_TOKEN:
    st.error("GH_TOKEN yoxdur. GitHub Actions-i işə salmaq mümkün deyil.")
    st.stop()

st.title("🎬 Talyhs Studio")
st.caption("Mövzunu seç, videonu hazırla, nəticəni yoxla və yayımlanmanı idarə et.")

def github_get(path, params=None):
    response = requests.get(f"{API}/repos/{REPO}/{path}", headers=HEADERS, params=params, timeout=20)
    response.raise_for_status()
    return response.json()

def github_dispatch(inputs):
    url = f"{API}/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches"
    response = requests.post(url, headers=HEADERS, json={"ref": "main", "inputs": inputs}, timeout=20)
    if response.status_code not in (204,):
        raise RuntimeError(f"GitHub API cavabı: {response.status_code} — {response.text[:500]}")
    
def status_badge(status, conclusion):
    if status == "in_progress":
        return "🟡 İcra olunur"
    if status == "queued":
        return "⏳ Növbədə"
    if conclusion == "success":
        return "✅ Uğurlu"
    if conclusion == "failure":
        return "❌ Xəta"
    if conclusion == "cancelled":
        return "⏹️ Dayandırılıb"
    return status or "Naməlum"

tab_create, tab_history, tab_help = st.tabs(["➕ Video hazırla", "📋 İcra tarixçəsi", "⚙️ Quraşdırma"])

with tab_create:
    left, right = st.columns([1.35, 1])
    with left:
        topic = st.text_input("Video mövzusu", placeholder="Məsələn: Süni intellekt haqqında 10 maraqlı fakt")
        language = st.selectbox("Dil", ["Azərbaycan dili", "English", "Türkçe"], index=0)
        video_format = st.radio("Format", ["Shorts / şaquli 9:16", "Standart / üfüqi 16:9"], horizontal=False)
        duration_label = st.selectbox("Müddət", ["30 saniyə", "1 dəqiqə", "3 dəqiqə", "5 dəqiqə"], index=2)
        voice = st.selectbox("Səs", ["Avtomatik", "Kişi səsi", "Qadın səsi"], index=0)
    with right:
        stock = st.multiselect("Stok video mənbələri", ["Pixabay", "Pexels"], default=["Pixabay", "Pexels"])
        subtitles = st.checkbox("Sinxron subtitrlər əlavə et", value=True)
        thumbnail = st.checkbox("Thumbnail şəkli yarat", value=True)
        seo = st.checkbox("SEO başlıq və təsvir hazırla", value=True)
        privacy_label = st.selectbox("YouTube görünməsi", ["Private — yalnız mən", "Unlisted — linki olanlar", "Public — hamı"], index=0)
        publish_mode = st.selectbox("Yayımlama rejimi", ["Hazırla, yayımlama", "Hazırla və seçilmiş görünmə ilə yüklə"], index=0)
        schedule = st.checkbox("Təyin olunmuş vaxtda yayımlama (əlavə quraşdırma tələb edir)", value=False, disabled=True)
    durations = {"30 saniyə": "30", "1 dəqiqə": "60", "3 dəqiqə": "180", "5 dəqiqə": "300"}
    languages = {"Azərbaycan dili": "az", "English": "en", "Türkçe": "tr"}
    privacy = {"Private — yalnız mən": "private", "Unlisted — linki olanlar": "unlisted", "Public — hamı": "public"}
    voices = {"Avtomatik": "auto", "Kişi səsi": "male", "Qadın səsi": "female"}
    providers = ",".join(stock) if stock else "Pixabay"
    st.info("İctimai yayımlamadan əvvəl nəticəni yoxlamaq tövsiyə olunur. İlk mərhələdə panel GitHub Actions-i işə salır; MP4 və subtitrlər workflow artifact kimi saxlanılır.")
    if st.button("🚀 Video istehsalını başlat", type="primary", use_container_width=True):
        if not topic.strip():
            st.error("Əvvəlcə video mövzusunu daxil et.")
        else:
            inputs = {
                "topic": topic.strip()[:180],
                "language": languages[language],
                "duration": durations[duration_label],
                "video_format": "vertical" if video_format.startswith("Shorts") else "horizontal",
                "voice": voices[voice],
                "stock_sources": providers,
                "subtitles": "true" if subtitles else "false",
                "thumbnail": "true" if thumbnail else "false",
                "seo": "true" if seo else "false",
                "privacy": privacy[privacy_label],
                "publish": "upload" if publish_mode.startswith("Hazırla və") else "prepare",
            }
            try:
                github_dispatch(inputs)
                st.success("GitHub Actions işə salınması qəbul edildi. İcra tarixçəsi bölməsindən vəziyyəti yoxla.")
            except requests.RequestException as exc:
                st.error(f"GitHub ilə əlaqə xətası: {exc}")
            except Exception as exc:
                st.error(str(exc))

with tab_history:
    st.subheader("Son icralar")
    if st.button("🔄 Yenilə"):
        st.rerun()
    try:
        data = github_get(f"actions/workflows/{WORKFLOW}/runs", {"per_page": 10})
        runs = data.get("workflow_runs", [])
        if not runs:
            st.info("Hələ icra tarixçəsi yoxdur.")
        for run in runs:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"**{run.get('display_title') or run.get('name') or 'Video işi'}**")
                    st.caption(f"Başlanma: {run.get('created_at', '').replace('T', ' ').replace('Z', ' UTC')} · #{run.get('run_number')}")
                    st.write(status_badge(run.get("status"), run.get("conclusion")))
                with c2:
                    st.link_button("GitHub logları", run.get("html_url", "https://github.com"))
                if run.get("conclusion") == "success":
                    try:
                        artifacts = github_get(f"actions/runs/{run['id']}/artifacts").get("artifacts", [])
                        if artifacts:
                            st.caption("Saxlanmış fayllar: " + ", ".join(a.get("name", "artifact") for a in artifacts))
                    except requests.RequestException:
                        pass
    except requests.RequestException as exc:
        st.error(f"Tarixçə oxunmadı: {exc}")

with tab_help:
    st.subheader("Quraşdırma")
    st.markdown("""
    Paneli hostingdə işə salmaq üçün serverdə bu mühit dəyişənləri qurulmalıdır:

    - `DASHBOARD_PASSWORD` — panelə giriş üçün güclü, ayrıca şifrə.
    - `GH_TOKEN` — yalnız bu repoda Actions işə salmaq icazəsi olan GitHub tokeni.
    - `GITHUB_REPOSITORY` — standart olaraq `Talyhs/youtubeotumsi`.
    - `GITHUB_WORKFLOW_FILE` — standart olaraq `main.yml`.

    **Tokeni və API açarlarını heç vaxt brauzerə, HTML/JavaScript-ə və ya açıq repoya yerləşdirmə.**
    Render üçün `render.yaml` konfiqurasiyası əlavə olunur, amma canlı URL yalnız hosting hesabında deploy edildikdən sonra yaranacaq.
    """)
    st.link_button("GitHub layihəsi", f"https://github.com/{REPO}")
    st.link_button("GitHub Actions", f"https://github.com/{REPO}/actions")
