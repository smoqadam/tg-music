# Telegram Saved Messages Audio Downloader

Downloads audio files you send or forward to a Telegram chat and stores them on disk.

## Setup

1. Create a Telegram API app at <https://my.telegram.org/apps>.
2. Copy `.env.example` to `.env` and set `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`.
3. Run the first login in the foreground:

```sh
docker compose run --rm tg-audio-login
```

Enter your Telegram phone number, login code, and 2FA password if prompted. When you see `Listening for audio in Saved Messages`, press `Ctrl+C`.

4. Start the background service:

```sh
docker compose up -d --build
```

After login, the session is saved under `./sessions`, so normal detached runs will work without logging in again.

If the background container exits with `Telegram is not logged in yet`, run the login command above once and then start it again.

Downloaded files are written to `./downloads` by default. Change the host path in `docker-compose.yml` if you want to store them elsewhere on the Raspberry Pi.

## Recommended Telegram Setup

To avoid polluting Saved Messages, create a private channel such as `Audio Inbox`, keep it private, and set:

```env
TELEGRAM_SOURCE_CHAT=Audio Inbox
```

Then forward audio files to that channel. You can also use a private group, but a private channel is cleaner because it behaves like a one-person inbox.

## Configuration

- `TELEGRAM_API_ID`: Telegram API ID from my.telegram.org.
- `TELEGRAM_API_HASH`: Telegram API hash from my.telegram.org.
- `TELEGRAM_SESSION_PATH`: session file path inside the container.
- `DOWNLOAD_DIR`: download destination inside the container.
- `TELEGRAM_SOURCE_CHAT`: chat to monitor. Use `me` for Saved Messages, an exact private channel/group title, a public username/link, or a numeric chat ID.
- `AUDIO_EXTENSIONS`: optional comma-separated allowlist. Leave empty to save every Telegram audio or voice message.

The service only listens to the configured source chat and ignores non-audio media.

## Diagnose

If the service starts but does not download, run:

```sh
docker compose run --rm tg-audio-diagnose
```

This prints the dialogs visible to the Telegram session and the recent messages/media metadata in the configured source chat.
