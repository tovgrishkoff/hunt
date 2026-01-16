import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
import json

async def test():
    with open('accounts_config.json') as f:
        accounts = json.load(f)
    
    for acc in accounts:
        print(f"Testing {acc['session_name']}...")
        string_session = acc.get('string_session')
        if string_session:
            client = TelegramClient(
                StringSession(string_session),
                int(acc['api_id']),
                acc['api_hash']
            )
            print(f"  Created client, connecting...")
            await client.connect()
            print(f"  Connected! Authorized: {await client.is_user_authorized()}")
            await client.disconnect()
            print(f"  ✅ Success!")
        else:
            print(f"  No string_session")

asyncio.run(test())
