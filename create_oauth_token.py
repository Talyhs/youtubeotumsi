
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secrets.json",
    SCOPES,
)

credentials = flow.run_local_server(
    port=0,
    access_type="offline",
    prompt="consent",
)

with open("token.json", "w", encoding="utf-8") as file:
    file.write(credentials.to_json())

if not credentials.refresh_token:
    raise RuntimeError(
        "No refresh token was returned. Recheck OAuth consent "
        "and offline access settings."
    )

print("OAuth token created successfully.")
