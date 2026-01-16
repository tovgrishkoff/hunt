#!/usr/bin/env python3
"""
Проверка старой сессии с новым прокси
Попытка использовать существующую string_session с обновленным прокси
"""
import asyncio
import json
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from urllib.parse import urlparse

def parse_proxy(proxy_config):
    """Парсинг прокси в формат для Telethon"""
    if not proxy_config:
        return None
    
    if isinstance(proxy_config, str):
        try:
            parsed = urlparse(proxy_config)
            proxy_type = parsed.scheme.lower()
            host = parsed.hostname
            port = parsed.port or (8080 if proxy_type in ['http', 'https'] else 1080)
            username = parsed.username
            password = parsed.password
            
            if not host or not port:
                return None
            
            if proxy_type in ['http', 'https']:
                proxy_dict = {
                    'proxy_type': 'http',
                    'addr': host,
                    'port': port
                }
                if username:
                    proxy_dict['username'] = username
                if password:
                    proxy_dict['password'] = password
                return proxy_dict
        except Exception as e:
            print(f"⚠️ Ошибка парсинга прокси: {e}")
            return None
    
    return None

async def test_session(session_name, string_session, proxy_config):
    """Проверка работы старой сессии с новым прокси"""
    print("\n" + "="*80)
    print(f"🧪 ПРОВЕРКА СЕССИИ: {session_name}")
    print("="*80)
    
    # Загружаем данные аккаунта
    config_file = Path('accounts_config.json')
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    account = None
    for acc in accounts:
        if acc['session_name'] == session_name:
            account = acc
            break
    
    if not account:
        print(f"❌ Аккаунт {session_name} не найден в accounts_config.json")
        return False
    
    api_id = int(account['api_id'])
    api_hash = account['api_hash']
    phone = account['phone']
    
    print(f"📱 Телефон: {phone}")
    print(f"🔑 API ID: {api_id}")
    print(f"🔗 Прокси: {proxy_config[:50]}...")
    print()
    
    # Парсим прокси
    proxy = parse_proxy(proxy_config)
    if proxy:
        print(f"🔗 Используем прокси: {proxy['addr']}:{proxy['port']}")
    else:
        print("⚠️ Прокси не используется")
    
    # Создаем клиент со старой StringSession
    try:
        session_obj = StringSession(string_session)
        client = TelegramClient(session_obj, api_id, api_hash, proxy=proxy)
        
        print("\n🔌 Подключение к Telegram...")
        try:
            await asyncio.wait_for(client.connect(), timeout=30.0)
            print("✅ Подключение установлено")
        except asyncio.TimeoutError:
            print("❌ Таймаут подключения")
            await client.disconnect()
            return False
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            try:
                await client.disconnect()
            except:
                pass
            return False
        
        # Проверяем авторизацию
        if await client.is_user_authorized():
            print("✅ Сессия валидна! Аккаунт авторизован")
            
            # Получаем информацию о пользователе
            try:
                me = await client.get_me()
                username = getattr(me, 'username', 'No username')
                first_name = getattr(me, 'first_name', 'No name')
                print(f"✅ Авторизован как: {first_name} (@{username})")
                print(f"   User ID: {me.id}")
                print(f"   Телефон: {me.phone}")
                
                await client.disconnect()
                
                print("\n" + "="*80)
                print("✅ СТАРАЯ СЕССИЯ РАБОТАЕТ С НОВЫМ ПРОКСИ!")
                print("="*80)
                print("\n💡 Можно использовать старую сессию, прокси уже обновлены в accounts_config.json")
                print("   Просто перезапустите контейнеры:")
                print("   docker-compose restart account-manager marketer")
                
                return True
            except Exception as e:
                print(f"⚠️ Ошибка при получении информации: {e}")
                await client.disconnect()
                return False
        else:
            print("❌ Сессия не валидна или аккаунт не авторизован")
            await client.disconnect()
            return False
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        try:
            await client.disconnect()
        except:
            pass
        return False

async def main():
    """Основная функция"""
    print("\n" + "="*80)
    print("🧪 ПРОВЕРКА СТАРЫХ СЕССИЙ С НОВЫМИ ПРОКСИ")
    print("="*80)
    print("\nПроверяем, работают ли старые сессии с новыми прокси...\n")
    
    # Загружаем accounts_config.json
    config_file = Path('accounts_config.json')
    if not config_file.exists():
        print(f"❌ Файл {config_file} не найден!")
        return
    
    with open(config_file, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    # Тестируем оба аккаунта
    accounts_to_test = [
        'promotion_oleg_petrov',
        'promotion_anna_truncher'
    ]
    
    results = {}
    
    for session_name in accounts_to_test:
        account = None
        for acc in accounts:
            if acc['session_name'] == session_name:
                account = acc
                break
        
        if not account:
            print(f"⚠️ Аккаунт {session_name} не найден, пропускаем")
            continue
        
        result = await test_session(
            session_name,
            account['string_session'],
            account['proxy']
        )
        results[session_name] = result
        
        # Пауза между тестами
        if session_name != accounts_to_test[-1]:
            print("\n⏸️ Пауза 3 секунды...")
            await asyncio.sleep(3)
    
    # Итоги
    print("\n" + "="*80)
    print("📊 ИТОГИ ПРОВЕРКИ")
    print("="*80)
    
    for session_name, result in results.items():
        status = "✅ РАБОТАЕТ" if result else "❌ НЕ РАБОТАЕТ"
        print(f"{session_name}: {status}")
    
    working = sum(1 for r in results.values() if r)
    if working > 0:
        print(f"\n✅ {working} из {len(results)} сессий работают!")
        print("\n💡 Можно использовать старые сессии, просто перезапустите контейнеры")
    else:
        print(f"\n❌ Ни одна из сессий не работает")
        print("\n💡 Нужна переавторизация или создание новых сессий")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
    except Exception as e:
        print(f"\n\n❌ Критическая ошибка: {e}")
