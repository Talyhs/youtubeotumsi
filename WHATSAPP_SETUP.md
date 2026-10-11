# WhatsApp control setup (Talyhs Studio)

## What this first integration does

- Receives WhatsApp text messages through the official Meta WhatsApp Cloud API webhook.
- Accepts `hazırla: <topic>` and starts the existing GitHub Actions workflow in **prepare-only** mode.
- Accepts `status` to report the latest workflow run and `kömək` to show commands.
- Replies to the WhatsApp sender with a GitHub Actions link.
- Verifies Meta's webhook signature and only accepts commands from `WHATSAPP_ALLOWED_PHONE`.

## Important current limitation

This first stage does **not** upload the prepared MP4 after a WhatsApp approval. The current GitHub workflow stores the MP4 as a temporary Actions artifact (7-day retention), and it has no secure, durable hand-off from a WhatsApp approval message to a later YouTube upload of that exact same file. For safety, approval commands do not publish anything. The next stage must add secure artifact storage and a separate, explicit approval/upload workflow before that behavior can be enabled.

Scheduled commands such as “tomorrow at 14:00” are also not implemented in this first stage; commands currently start preparation immediately.

## 1. Meta / WhatsApp Business Platform

The WhatsApp Business mobile app alone does not provide an inbound webhook for this bot. Set up the official WhatsApp Business Platform Cloud API in Meta for Developers and connect a business phone number. Depending on the number and account setup, migration/coexistence eligibility can differ; do not remove the number from the mobile app until Meta's current onboarding flow confirms the supported path.

In Meta's app dashboard:

1. Add/configure the WhatsApp product and a WhatsApp Business Account.
2. Configure the webhook callback URL as `https://<your-whatsapp-render-service>.onrender.com/webhook`.
3. Set the webhook verify token to the exact value you choose for `WHATSAPP_VERIFY_TOKEN`.
4. Subscribe the WhatsApp Business Account to the `messages` webhook field.
5. Obtain the permanent/system-user access token, phone number ID, and Meta app secret using Meta's official setup flow.

## 2. Render environment variables

The new `talyhs-whatsapp-control` service needs these environment variables. Add values in Render's Environment screen only; never commit them to GitHub or send them in chat.

- `WHATSAPP_TOKEN`: Cloud API access token.
- `WHATSAPP_PHONE_NUMBER_ID`: phone number ID from Meta.
- `WHATSAPP_VERIFY_TOKEN`: a long, random verification string you create.
- `META_APP_SECRET`: Meta app secret used to verify webhook signatures.
- `WHATSAPP_ALLOWED_PHONE`: your own WhatsApp number in international format, digits only, e.g. country code + number without `+` or spaces.
- `GH_TOKEN`: GitHub token with Actions read/write permission for this repository.
- `GITHUB_REPOSITORY`: `Talyhs/youtubeotumsi`.
- `GITHUB_WORKFLOW_FILE`: `main.yml`.
- `WHATSAPP_GRAPH_VERSION`: Graph API version supported by the Meta app, initially configured as `v23.0`; update it to a version currently supported by Meta if required.

The existing Streamlit service and the WhatsApp webhook are separate Render services. After the branch is merged, sync/update the Render Blueprint or create the new service from the same repository and branch. Confirm that the webhook service's public URL opens `/health` and returns JSON with `ok: true`.

## 3. Test commands

Send these from the allow-listed WhatsApp number:

- `kömək`
- `hazırla: Toz şəkərin tarladan süfrəyə səyahəti`
- `status`

The first stage uses Turkish, 601 seconds, horizontal format, Pexels + Pixabay, subtitles and thumbnail enabled, and `publish=prepare`. It must not upload to YouTube.

## 4. Security and approval workflow

- Use a GitHub fine-grained token restricted to this repository and the Actions permissions it needs.
- Restrict commands to your own allow-listed number.
- Keep secrets in Render environment variables and GitHub Actions secrets only.
- Before enabling approval-based publishing, add secure artifact storage (for example a private object store with expiring signed URLs), bind the artifact to a unique job ID, and require an explicit `təsdiq <job-id>` command. The upload job must use the exact approved MP4, validate the sender again, and default to no upload.
