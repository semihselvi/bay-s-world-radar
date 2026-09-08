from __future__ import annotations

import getpass
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"


def _read_env_lines() -> list[str]:
    if not ENV_PATH.exists():
        return []
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def _upsert(lines: list[str], key: str, value: str) -> list[str]:
    prefix = key + "="
    out: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(prefix):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    return out


def _validate_bot(token: str) -> dict:
    response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20)
    data = response.json()
    if response.status_code != 200 or not data.get("ok"):
        raise RuntimeError("Telegram bot token is invalid or Telegram could not be reached.")
    return data.get("result") or {}


def _latest_private_chat_id(token: str) -> str:
    response = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=25)
    data = response.json()
    if response.status_code != 200 or not data.get("ok"):
        return ""
    updates = data.get("result") or []
    for update in reversed(updates):
        for key in ("message", "edited_message", "channel_post"):
            message = update.get(key) or {}
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id is not None:
                return str(chat_id)
    return ""


def _send_test(token: str, chat_id: str) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": "✅ BAY-S Facebook Radar Telegram bağlantısı hazır.",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    data = response.json()
    if response.status_code != 200 or not data.get("ok"):
        raise RuntimeError("Bot token works, but the test message could not be delivered to this chat.")


def main() -> int:
    print("BAY-S FACEBOOK RADAR - TELEGRAM SETUP")
    print("Bot token is entered only in this local window and is not uploaded to GitHub.")
    print("")

    token = getpass.getpass("Telegram bot token (hidden): ").strip()
    if not token:
        print("No token entered. Cancelled.")
        return 1

    bot = _validate_bot(token)
    username = bot.get("username") or "your bot"
    print(f"Bot verified: @{username}")
    print("")
    print(f"1) Open Telegram and send any message to @{username}.")
    input("2) After sending the message, press ENTER here: ")

    chat_id = _latest_private_chat_id(token)
    if chat_id:
        print("Chat detected automatically.")
    else:
        chat_id = input("Chat could not be detected automatically. Enter TELEGRAM_CHAT_ID: ").strip()
    if not chat_id:
        print("No chat ID available. Cancelled.")
        return 1

    _send_test(token, chat_id)

    lines = _read_env_lines()
    lines = _upsert(lines, "TELEGRAM_BOT_TOKEN", token)
    lines = _upsert(lines, "TELEGRAM_CHAT_ID", chat_id)
    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    print("")
    print("TELEGRAM READY")
    print("A test message was sent successfully.")
    print(f"Saved locally to: {ENV_PATH}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\nTELEGRAM_SETUP_ERROR: {exc}")
        raise SystemExit(1)
