#!/usr/bin/env python3
"""
Переавторизация заблокированных Bali-аккаунтов через QR-код.

Использует прокси из accounts_config.json — важно, чтобы сессия создавалась
с тем же прокси, с которым будет работать в production.

Использование:
    python3 scripts/reauth_bali_blocked_accounts.py
    python3 scripts/reauth_bali_blocked_accounts.py promotion_oleg_petrov promotion_Masha Sinugina
"""
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

# По умолчанию — заблокированные аккаунты
DEFAULT_SESSIONS = ["promotion_oleg_petrov", "promotion_Masha Sinugina"]

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "accounts_config.json"


def parse_proxy(proxy_string: str):
    """Парсинг прокси из строки http://user:pass@host:port"""
    if not proxy_string:
        return None
    try:
        parsed = urlparse(proxy_string)
        scheme = parsed.scheme.lower()
        if scheme in ("http", "https"):
            return {
                "proxy_type": "http",
                "addr": parsed.hostname,
                "port": parsed.port or 8080,
                "username": parsed.username,
                "password": parsed.password,
            }
        if scheme == "socks5":
            return {
                "proxy_type": "socks5",
                "addr": parsed.hostname,
                "port": parsed.port or 1080,
                "username": parsed.username,
                "password": parsed.password,
            }
    except Exception as e:
        print(f"⚠️ Ошибка парсинга прокси: {e}")
    return None


def display_qr(url: str) -> None:
    if QR_AVAILABLE:
        try:
            qr = qrcode.QRCode()
            qr.add_data(url)
            qr.print_ascii(invert=True)
        except Exception as e:
            print(f"⚠️ Ошибка QR: {e}")
            print(f"\n📱 URL: {url}")
    else:
        print(f"\n📱 URL для сканирования:\n{url}")
        print("\n   Telegram → Настройки → Устройства → Подключить устройство")


async def reauth_account(account: dict) -> str | None:
    """Переавторизация через QR. Возвращает новый string_session или None."""
    session_name = account["session_name"]
    api_id = int(account["api_id"])
    api_hash = account["api_hash"]
    phone = account.get("phone", "")
    nickname = account.get("nickname", session_name)

    proxy_config = parse_proxy(account.get("proxy"))
    if proxy_config:
        print(f"   🔗 Прокси: {proxy_config['addr']}:{proxy_config['port']}")

    print(f"\n📱 {nickname} ({session_name})")
    print("   Подключение...")

    client = TelegramClient(
        StringSession(),
        api_id,
        api_hash,
        proxy=proxy_config,
    )

    try:
        await client.connect()
        if not await client.is_user_authorized():
            print("   QR-авторизация (сессия сброшена)")
            qr_login = await client.qr_login()
            print("\n   Отсканируйте QR в Telegram:")
            print("   Настройки → Устройства → Подключить устройство\n")
            display_qr(qr_login.url)
            print("\n   Ожидание сканирования (до 2 мин)...")

            try:
                await asyncio.wait_for(qr_login.wait(), timeout=120)
            except SessionPasswordNeededError:
                pwd = input("   Пароль 2FA: ").strip()
                await client.sign_in(password=pwd)
            except asyncio.TimeoutError:
                print("   ❌ Время вышло")
                await client.disconnect()
                return None

        me = await client.get_me()
        session_string = client.session.save()
        print(f"   ✅ @{getattr(me, 'username', '?')}")
        await client.disconnect()
        return session_string

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        try:
            await client.disconnect()
        except Exception:
            pass
        return None


def main():
    sessions_to_auth = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_SESSIONS

    if not CONFIG_PATH.exists():
        print(f"❌ Не найден {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        accounts = json.load(f)

    by_session = {acc["session_name"]: acc for acc in accounts if acc.get("session_name")}
    to_process = []
    for s in sessions_to_auth:
        if s in by_session:
            to_process.append(by_session[s])
        else:
            print(f"⚠️ Аккаунт {s} не найден в конфиге")

    if not to_process:
        print("❌ Нет аккаунтов для переавторизации")
        sys.exit(1)

    print("=" * 60)
    print("🔄 ПЕРЕАВТОРИЗАЦИЯ BALI-АККАУНТОВ (QR + прокси)")
    print("=" * 60)

    for account in to_process:
        new_session = asyncio.run(reauth_account(account))
        if new_session:
            account["string_session"] = new_session
            account["nickname"] = account.get("nickname", account["session_name"])

    if to_process:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(accounts, f, ensure_ascii=False, indent=2)
        print("\n✅ accounts_config.json обновлён")
        print("\n📋 Дальше:")
        print("   1. python3 scripts/update_all_accounts_from_config.py")
        print("   2. docker-compose restart account-manager marketer")


if __name__ == "__main__":
    main()
