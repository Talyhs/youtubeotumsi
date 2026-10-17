
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secrets.json",
    SCOPES
)

credentials = flow.run_local_server(
    port=0,
    access_type="offline",
    prompt="consent"
)

with open("token.json", "w", encoding="utf-8") as f:
    f.write(credentials.to_json())

data = json.loads(credentials.to_json())

if data.get("refresh_token"):
    print("Uğurlu: refresh_token yaradıldı.")
    print("token.json faylı hazırdır.")
else:
    print("XƏTA: refresh_token alınmadı.")
    print("Google hesabına yenidən icazə vermək lazımdır.")
