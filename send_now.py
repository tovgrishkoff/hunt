import json
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    with open('accounts_config.json', 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    account = accounts[0]

    with open('targets.txt', 'r', encoding='utf-8') as f:
        targets = [line.strip() for line in f if line.strip()]
    target = targets[0]

    with open('messages_general.txt', 'r', encoding='utf-8') as f:
        messages = [line.strip() for line in f if line.strip()]
    message = messages[0]

    client = TelegramClient(StringSession(account['string_session']), account['api_id'], account['api_hash'])
    await client.connect()
    print('authorized=', await client.is_user_authorized())
    try:
        await client.send_message(target, message)
        print('sent_to=', target)
    except Exception as e:
        print('error=', repr(e))
    finally:
        await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())


