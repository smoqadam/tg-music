import asyncio
import logging
import os
import re
import sys
from pathlib import Path

from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeAudio, MessageMediaDocument

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("tg-music")


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# Environment configuration
API_ID = int(required_env("TELEGRAM_API_ID"))
API_HASH = required_env("TELEGRAM_API_HASH")
SESSION_PATH = required_env("TELEGRAM_SESSION_PATH")
MUSIC_DIR = Path(os.getenv("MUSIC_DIR", "/music"))

# Where you paste links (your private "Musics" channel).
COMMAND_CHAT = required_env("COMMAND_CHAT")
# The bot that turns a link into audio files.
DOWNLOADER_BOT = required_env("DOWNLOADER_BOT")

UNKNOWN_ARTIST = os.getenv("UNKNOWN_ARTIST", "Unknown Artist")

configured_extensions = os.getenv("AUDIO_EXTENSIONS", "")
ALLOWED_EXTENSIONS = {
    extension.strip().lower().lstrip(".")
    for extension in configured_extensions.split(",")
    if extension.strip()
}

URL_PATTERN = re.compile(r"https?://\S+")
# Leading track number like "07 - " or "13. " at the start of a filename.
TRACK_PREFIX_PATTERN = re.compile(r"^\s*\d+\s*[-.]\s+")


def safe_name(value: str) -> str:
    """Filesystem-safe but keeps apostrophes, ampersands and commas."""
    cleaned = re.sub(r"[^\w.\-'&, ()]+", "_", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:180] or "audio"


def parse_artist_title(stem: str) -> tuple[str, str]:
    """Strip any leading track number, then split on the first ' - '."""
    without_track = TRACK_PREFIX_PATTERN.sub("", stem).strip()
    if " - " in without_track:
        artist, title = without_track.split(" - ", 1)
        artist = artist.strip()
        title = title.strip()
        if artist and title:
            return artist, title
    return UNKNOWN_ARTIST, without_track or stem


def destination_for(message) -> tuple[Path, str, str]:
    """Return (path, artist, title) for an audio message."""
    original = message.file.name if (message.file and message.file.name) else None
    suffix = Path(original).suffix if original else ""
    stem = Path(original).stem if original else f"telegram-audio-{message.id}"

    if not suffix and message.file and message.file.ext:
        suffix = message.file.ext

    artist, title = parse_artist_title(stem)
    filename = safe_name(f"{stem}{suffix}")
    folder = MUSIC_DIR / safe_name(artist)
    return folder / filename, artist, title


def is_audio_message(message) -> bool:
    if message.voice or message.audio:
        return True

    if message.file and message.file.mime_type:
        return message.file.mime_type.lower().startswith("audio/")

    if not isinstance(message.media, MessageMediaDocument) or not message.document:
        return False

    return any(
        isinstance(attribute, DocumentAttributeAudio)
        for attribute in message.document.attributes
    )


def extension_allowed(message) -> bool:
    if not ALLOWED_EXTENSIONS:
        return True
    extension = ""
    if message.file and message.file.ext:
        extension = message.file.ext.lower().lstrip(".")
    return extension in ALLOWED_EXTENSIONS


async def resolve_chat(client: TelegramClient, ref: str):
    # 1. Direct integer ID
    try:
        return await client.get_entity(int(ref))
    except ValueError:
        pass

    # 2. Look through open dialogs (handles private channel titles).
    async for dialog in client.iter_dialogs():
        if dialog.name == ref:
            return dialog.entity
        username = getattr(dialog.entity, "username", None)
        if username and f"@{username.lower()}" == ref.lower():
            return dialog.entity

    # 3. Fallback: resolve directly by username/link.
    try:
        return await client.get_entity(ref)
    except Exception:
        pass

    raise RuntimeError(
        f"Could not find Telegram chat {ref!r}. "
        "Ensure you provided the exact @username, title, or chat ID."
    )


async def main() -> None:
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    Path(SESSION_PATH).parent.mkdir(parents=True, exist_ok=True)

    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized() and not sys.stdin.isatty():
        raise RuntimeError(
            "Telegram is not logged in yet. Run your login container profile first."
        )

    await client.start()

    command_chat = await resolve_chat(client, COMMAND_CHAT)
    bot_chat = await resolve_chat(client, DOWNLOADER_BOT)
    bot_id = getattr(bot_chat, "id", bot_chat)

    logger.info(
        "Connected. Commands from %r -> relay to %r, saving under %s",
        COMMAND_CHAT,
        DOWNLOADER_BOT,
        MUSIC_DIR,
    )

    # 1. You paste a link into the Musics channel -> relay it to the bot.
    @client.on(events.NewMessage(chats=command_chat))
    async def handle_command(event: events.NewMessage.Event) -> None:
        text = event.message.raw_text or ""
        urls = URL_PATTERN.findall(text)
        if not urls:
            return
        for url in urls:
            logger.info("Relaying link to %s: %s", DOWNLOADER_BOT, url)
            await client.send_message(bot_chat, url)

    # 2. The bot replies with audio -> download into the artist folder.
    @client.on(events.NewMessage(chats=bot_chat))
    async def handle_bot_reply(event: events.NewMessage.Event) -> None:
        message = event.message
        if message.sender_id != bot_id:
            return
        if not is_audio_message(message) or not extension_allowed(message):
            return

        destination, artist, title = destination_for(message)
        destination.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Downloading %s -> %s", title, destination)

        await message.download_media(file=str(destination))
        logger.info("Saved %s", destination)

        await client.send_message(command_chat, f"✅ {artist} — {title}")

    logger.info("Listening for links and downloads...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped")
