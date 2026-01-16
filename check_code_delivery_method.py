#!/usr/bin/env python3
"""
Проверка метода доставки кода
Показывает детальную информацию о том, куда Telegram отправляет код
"""
import asyncio
from telethon import TelegramClient

# Данные аккаунтов
ACCOUNTS = {
    "1": {
        "phone": "+380935173511",
        "api_id": 37120288,
        "api_hash": "e576f165ace9ea847633a136dc521062",
        "session_name": "promotion_anna_truncher",
        "nickname": "Anna Truncher"
    },
    "2": {
        "phone": "+380931849825",
        "api_id": 34601626,
        "api_hash": "eba8c7b793884b92a65c48436b646600",
        "session_name": "promotion_artur_biggest",
        "nickname": "Artur Biggest"
    },
    "3": {
        "phone": "+380630429234",
        "api_id": 33336443,
        "api_hash": "9d9ee718ff58f43ccbcf028a629528fd",
        "session_name": "promotion_andrey_virgin",
        "nickname": "Andrey Virgin"
    }
}

async def check_code_delivery(account_data):
    """Проверка метода доставки кода"""
    phone = account_data["phone"]
    api_id = account_data["api_id"]
    api_hash = account_data["api_hash"]
    session_name = f"check_{account_data['session_name']}"
    
    print(f"\n{'='*80}")
    print(f"🔍 Проверка доставки кода: {account_data['nickname']} ({phone})")
    print(f"{'='*80}")
    
    import os
    os.makedirs("sessions", exist_ok=True)
    
    client = TelegramClient(f"sessions/{session_name}", api_id, api_hash)
    
    try:
        print("🔐 Подключение...")
        await asyncio.wait_for(client.connect(), timeout=30.0)
        print("✅ Подключено")
        
        print("\n📲 Отправка запроса на код...")
        result = await asyncio.wait_for(
            client.send_code_request(phone),
            timeout=60.0
        )
        
        print("\n" + "="*80)
        print("📊 РЕЗУЛЬТАТ ЗАПРОСА КОДА:")
        print("="*80)
        print(f"Тип доставки: {result.type}")
        print(f"Phone code hash: {result.phone_code_hash}")
        print(f"Next type: {getattr(result, 'next_type', 'N/A')}")
        print(f"Timeout: {getattr(result, 'timeout', 'N/A')} секунд")
        
        # Детальный анализ типа доставки
        result_type_str = str(result.type).lower()
        print("\n" + "="*80)
        print("🔍 АНАЛИЗ:")
        print("="*80)
        
        if 'sms' in result_type_str:
            print("✅ Код отправлен по SMS")
            print("   Проверьте SMS на номер", phone)
        elif 'telegram' in result_type_str or 'app' in result_type_str:
            print("⚠️ Код отправлен в Telegram на уже авторизованное устройство!")
            print("   Проверьте:")
            print("   1. Telegram на Android устройстве")
            print("   2. Веб-версию Telegram (web.telegram.org)")
            print("   3. Telegram Desktop (если установлен)")
            print("   Код должен прийти в уведомлениях")
        elif 'call' in result_type_str:
            print("📞 Код будет отправлен голосовым звонком")
            print("   Ответьте на звонок и прослушайте код")
        else:
            print(f"❓ Неизвестный тип доставки: {result.type}")
            print("   Проверьте все возможные места получения кода")
        
        print("\n" + "="*80)
        print("💡 РЕКОМЕНДАЦИИ:")
        print("="*80)
        
        if 'telegram' in result_type_str or 'app' in result_type_str:
            print("1. Откройте Telegram на Android/веб")
            print("2. Проверьте уведомления - код должен быть там")
            print("3. Или может появиться запрос на подтверждение новой авторизации")
            print("4. Если код не приходит - выйдите из аккаунта на всех устройствах")
            print("5. Попробуйте снова - тогда код придет по SMS")
        else:
            print("1. Проверьте указанный метод доставки")
            print("2. Если код не приходит - подождите 2-3 минуты")
            print("3. Попробуйте запросить код снова")
        
        await client.disconnect()
        
        # Удаляем тестовую сессию
        try:
            session_file = f"sessions/{session_name}.session"
            if os.path.exists(session_file):
                os.remove(session_file)
        except:
            pass
        
        return True
        
    except asyncio.TimeoutError:
        print("\n❌ Таймаут!")
        print("   Telegram не отвечает")
        try:
            await client.disconnect()
        except:
            pass
        return False
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        try:
            await client.disconnect()
        except:
            pass
        return False

def main():
    print("🔍 Проверка метода доставки кода")
    print("="*80)
    print("Показывает, куда именно Telegram отправляет код")
    print("="*80)
    print("\nВыберите аккаунт:")
    print()
    
    for key, account in ACCOUNTS.items():
        print(f"  {key}. {account['nickname']} ({account['phone']})")
    
    print()
    choice = input("Введите номер аккаунта (1-3): ").strip()
    
    if choice not in ACCOUNTS:
        print(f"❌ Неверный выбор: {choice}")
        return
    
    account = ACCOUNTS[choice]
    print(f"\n✅ Выбран: {account['nickname']} ({account['phone']})")
    
    asyncio.run(check_code_delivery(account))

if __name__ == "__main__":
    main()

