# ElevenLabs Azerbaijani narration setup

The workflow uses ElevenLabs for narration when both of these GitHub Actions secrets are configured:

- `ELEVENLABS_API_KEY`: API key from your ElevenLabs account.
- `ELEVENLABS_VOICE_ID`: ID of a voice you have access to and have tested with Azerbaijani text.

The workflow defaults to `VOICE_PROVIDER=auto`. If both secrets exist, it uses ElevenLabs; if neither exists, it falls back to Edge TTS. If only one is set, the workflow fails clearly rather than silently using a different voice.

## Recommended model

The default is `eleven_v3`, because ElevenLabs documents Azerbaijani support for this model family. `eleven_multilingual_v2` does not list Azerbaijani among its supported languages. See the official language list: https://elevenlabs.io/docs/help-center/other/what-languages-do-you-support

## Configure the secrets

1. Open https://github.com/Talyhs/youtubeotumsi/settings/secrets/actions
2. Select **New repository secret**.
3. Add `ELEVENLABS_API_KEY` and paste the API key from https://elevenlabs.io/app/settings/api-keys.
4. Add `ELEVENLABS_VOICE_ID`. Find a voice in the Voice Library and copy its voice ID. Prefer a voice trained for Azerbaijani, or a permitted voice clone recorded in Azerbaijani.
5. Save both secrets. Do not put either value in source code, issues, logs, or chat.

## Important

- ElevenLabs usage may consume paid or plan-limited character quota.
- The generated narration is not time-stretched by FFmpeg. Video duration follows the actual narration duration, which helps preserve natural speech.
- The current subtitle timing is still estimated from the script rather than generated from exact speech timestamps. Review the final audio and subtitles before publishing.
- This integration has not been verified against a live ElevenLabs account until a workflow run completes with valid secrets.
