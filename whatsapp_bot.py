import hashlib
import hmac
import os
import re
from datetime import datetime, timezone

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

GRAPH_VERSION = os.getenv("WHATSAPP_GRAPH_VERSION", "v23.0")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "").strip()
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()
APP_SECRET = os.getenv("META_APP_SECRET", "").strip()
ALLOWED_PHONE = re.sub(r"\D", "", os.getenv("WHATSAPP_ALLOWED_PHONE", ""))
GH_TOKEN = os.getenv("GH_TOKEN", "").strip()
REPO = os.getenv("GITHUB_REPOSITORY", "Talyhs/youtubeotumsi").strip()
WORKFLOW = os.getenv("GITHUB_WORKFLOW_FILE", "main.yml").strip()
GITHUB_API = "https://api.github.com"
SESSION = requests.Session()


def configured():
    return all((WHATSAPP_TOKEN, PHONE_NUMBER_ID, VERIFY_TOKEN, APP_SECRET, ALLOWED_PHONE, GH_TOKEN))


def verify_signature(raw_body, signature):
    if not APP_SECRET or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        APP_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def send_text(to, body):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        raise RuntimeError("WhatsApp Cloud API konfiqurasiyası çatışmır.")
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{PHONE_NUMBER_ID}/messages"
    response = SESSION.post(
        url,
        headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
        json={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": body[:3500]},
        },
        timeout=20,
    )
    response.raise_for_status()


def github_headers():
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GH_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def dispatch_prepare(topic):
    if not GH_TOKEN:
        raise RuntimeError("GitHub tokeni konfiqurasiya edilməyib.")
    url = f"{GITHUB_API}/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches"
    inputs = {
        "topic": topic[:180],
        "language": "tr",
        "duration": "601",
        "video_format": "horizontal",
        "voice": "auto",
        "stock_sources": "Pixabay,Pexels",
        "subtitles": "true",
        "thumbnail": "true",
        "seo": "true",
        "privacy": "private",
        "publish": "prepare",
    }
    response = SESSION.post(
        url, headers=github_headers(), json={"ref": "main", "inputs": inputs}, timeout=20
    )
    if response.status_code != 204:
        raise RuntimeError(
            f"GitHub Actions cavabı {response.status_code}: {response.text[:300]}"
        )


def latest_run_summary():
    url = f"{GITHUB_API}/repos/{REPO}/actions/workflows/{WORKFLOW}/runs"
    response = SESSION.get(
        url, headers=github_headers(), params={"per_page": 1}, timeout=20
    )
    response.raise_for_status()
    runs = response.json().get("workflow_runs", [])
    if not runs:
        return "Hələ GitHub Actions icrası tapılmayıb."
    run = runs[0]
    status = run.get("status", "unknown")
    conclusion = run.get("conclusion") or "davam edir"
    return (
        f"Son iş: {run.get('display_title') or run.get('name')}\n"
        f"Vəziyyət: {status} / {conclusion}\n"
        f"İzləmə: {run.get('html_url')}"
    )


def handle_message(sender, body):
    if not ALLOWED_PHONE or re.sub(r"\D", "", sender) != ALLOWED_PHONE:
        return "Bu nömrə idarəetmə üçün icazəli deyil."
    command = body.strip()
    lowered = command.lower()

    if lowered in ("/help", "kömək", "help", "menyu"):
        return (
            "🎬 Talyhs Studio əmrləri\n"
            "• hazırla: video mövzusu — 10 dəqiqəlik türk videosu hazırla\n"
            "• status — son video işinin vəziyyəti\n"
            "• kömək — əmrləri göstər\n\n"
            "Hazırkı mərhələdə video yalnız hazırlanır; avtomatik yayımlanmır. "
            "Təsdiq ilə eyni MP4 faylının yüklənməsi ayrıca təsdiq axını tələb edir."
        )

    if lowered in ("status", "/status", "vəziyyət"):
        try:
            return latest_run_summary()
        except Exception:
            app.logger.exception("GitHub status query failed")
            return "İcra vəziyyətini oxumaq mümkün olmadı. GitHub Actions tarixçəsini yoxla."

    match = re.match(r"^(?:hazırla|hazirla|video)\s*[:\-]\s*(.+)$", command, re.I | re.S)
    if match:
        topic = match.group(1).strip()
        if len(topic) < 3:
            return "Mövzunu daha ətraflı yaz. Nümunə: hazırla: Toz şəkərin tarixçəsi"
        try:
            dispatch_prepare(topic)
            return (
                f"✅ Əmr qəbul edildi.\nMövzu: {topic[:180]}\n"
                "Parametrlər: türk dili, 10 dəqiqə, üfüqi video, stok görüntülər, "
                "səs, subtitrlər və thumbnail.\n"
                "YouTube-a yüklənməyəcək. İcra vəziyyətini görmək üçün “status” yaz.\n"
                f"İzləmə: https://github.com/{REPO}/actions"
            )
        except Exception:
            app.logger.exception("Could not dispatch workflow")
            return (
                "❌ Video işini başlatmaq mümkün olmadı. GitHub tokeninin Actions "
                "icazələrini və main.yml workflow parametrini yoxlamaq lazımdır."
            )

    if lowered.startswith(("təsdiq", "tesdiq", "approve", "yayımla", "yayimla")):
        return (
            "Təsdiq əmri hələ yayımlama etmir. Təhlükəsizlik üçün eyni MP4 faylını "
            "təsdiqdən sonra YouTube-a ötürən saxlama və təsdiq axını qurulmalıdır. "
            "Hazırda video hazırlanma rejimindədir."
        )

    return "Əmri başa düşmədim. “kömək” yazaraq nümunələrə bax."


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "whatsapp-control"}), 200


@app.get("/webhook")
def verify_webhook():
    mode = request.args.get("hub.mode", "")
    token = request.args.get("hub.verify_token", "")
    challenge = request.args.get("hub.challenge", "")
    if mode == "subscribe" and VERIFY_TOKEN and hmac.compare_digest(token, VERIFY_TOKEN):
        return challenge, 200
    return "Webhook verification failed", 403


@app.post("/webhook")
def receive_webhook():
    raw = request.get_data(cache=True)
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(raw, signature):
        return "Invalid signature", 401

    payload = request.get_json(silent=True) or {}
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    sender = str(message.get("from", ""))
                    if message.get("type") != "text":
                        send_text(sender, "Zəhmət olmasa, əmri mətn şəklində göndər.")
                        continue
                    body = message.get("text", {}).get("body", "")
                    reply = handle_message(sender, body)
                    send_text(sender, reply)
    except Exception:
        app.logger.exception("Webhook message processing failed")
        # Return 200 to avoid endless retries for a message already partially handled.
    return "EVENT_RECEIVED", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
