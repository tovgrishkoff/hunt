#!/usr/bin/env python3
"""
Скрипт для конвертации TData + Auth Key в String Session для Telethon

Использование:
1. Получите TData папку и Auth Key от продавца
2. Установите зависимости: pip install telethon
3. Запустите скрипт и следуйте инструкциям
"""
import asyncio
import json
import os
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import User


async def convert_tdata_to_string_session(tdata_path: str, auth_key: bytes, api_id: int, api_hash: str, dc_id: int = 2):
    """
    Конвертация TData + Auth Key в String Session
    
    Args:
        tdata_path: Путь к папке TData
        auth_key: Auth Key в виде bytes
        dc_id: Data Center ID (обычно 2 для Европы)
    """
    print("🔄 Конвертация TData + Auth Key в String Session...")
    
    # Создаем StringSession
    string_session = StringSession()
    
    # Устанавливаем DC и auth_key
    # Для Telethon нужно знать адрес сервера DC
    dc_addresses = {
        1: "149.154.175.50",
        2: "149.154.167.51",
        3: "149.154.175.100",
        4: "149.154.167.92",
        5: "91.108.56.100"
    }
    
    server_address = dc_addresses.get(dc_id, "149.154.167.51")
    port = 443
    
    try:
        # Устанавливаем DC и auth_key
        string_session.set_dc(dc_id, server_address, auth_key)
        
        # Создаем клиент для проверки
        client = TelegramClient(string_session, api_id, api_hash)
        
        print("🔌 Подключение к Telegram...")
        await client.connect()
        
        # Проверяем авторизацию
        if await client.is_user_authorized():
            me = await client.get_me()
            username = getattr(me, 'username', 'No username')
            first_name = getattr(me, 'first_name', 'No name')
            
            print(f"✅ Авторизация успешна!")
            print(f"👤 Аккаунт: {first_name} (@{username})")
            print(f"   ID: {me.id}")
            
            # Сохраняем String Session
            string_session_str = string_session.save()
            
            print("\n" + "="*80)
            print("📋 String Session (скопируйте это):")
            print("="*80)
            print(string_session_str)
            print("="*80)
            
            # Сохраняем в файл
            output_file = 'converted_string_session.txt'
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"API ID: {api_id}\n")
                f.write(f"API Hash: {api_hash}\n")
                f.write(f"DC ID: {dc_id}\n")
                f.write(f"Username: @{username}\n")
                f.write(f"First Name: {first_name}\n")
                f.write(f"User ID: {me.id}\n")
                f.write(f"\nString Session:\n{string_session_str}\n")
            
            print(f"\n✅ Сессия сохранена в файл: {output_file}")
            
            await client.disconnect()
            return string_session_str
        else:
            print("❌ Сессия не авторизована. Возможно, нужна дополнительная авторизация.")
            await client.disconnect()
            return None
            
    except Exception as e:
        print(f"❌ Ошибка при конвертации: {e}")
        return None


async def convert_from_auth_key_file(auth_key_file: str, api_id: int, api_hash: str, dc_id: int = 2):
    """
    Конвертация из файла с Auth Key (hex или base64)
    
    Args:
        auth_key_file: Путь к файлу с Auth Key
        api_id: API ID
        api_hash: API Hash
        dc_id: Data Center ID
    """
    print(f"📂 Чтение Auth Key из файла: {auth_key_file}")
    
    with open(auth_key_file, 'rb') as f:
        auth_key_data = f.read()
    
    # Пробуем разные форматы
    auth_key = None
    
    # Если это hex строка
    try:
        if len(auth_key_data) == 256:  # 256 байт = стандартный размер auth_key
            auth_key = auth_key_data
        elif len(auth_key_data) == 512:  # Возможно hex строка
            auth_key = bytes.fromhex(auth_key_data.decode('utf-8'))
        else:
            # Пробуем как hex
            try:
                auth_key = bytes.fromhex(auth_key_data.decode('utf-8').strip())
            except:
                # Пробуем как base64
                import base64
                auth_key = base64.b64decode(auth_key_data)
    except Exception as e:
        print(f"⚠️ Не удалось автоматически определить формат Auth Key: {e}")
        print("💡 Убедитесь, что Auth Key в формате:")
        print("   - 256 байт (бинарный файл)")
        print("   - Hex строка (512 символов)")
        print("   - Base64 строка")
        return None
    
    if not auth_key or len(auth_key) != 256:
        print(f"❌ Неверный размер Auth Key: {len(auth_key)} байт (ожидается 256)")
        return None
    
    return await convert_tdata_to_string_session("", auth_key, api_id, api_hash, dc_id)


async def interactive_conversion():
    """Интерактивная конвертация"""
    print("="*80)
    print("🔄 Конвертация TData + Auth Key в String Session")
    print("="*80)
    print()
    
    # Запрашиваем данные
    print("📋 Введите данные аккаунта:")
    api_id = input("API ID: ").strip()
    if not api_id:
        print("❌ API ID обязателен!")
        return
    
    api_hash = input("API Hash: ").strip()
    if not api_hash:
        print("❌ API Hash обязателен!")
        return
    
    try:
        api_id = int(api_id)
    except ValueError:
        print("❌ API ID должен быть числом!")
        return
    
    dc_id_input = input("DC ID (по умолчанию 2): ").strip()
    dc_id = int(dc_id_input) if dc_id_input else 2
    
    print()
    print("📂 Выберите способ ввода Auth Key:")
    print("1. Из файла (бинарный, hex или base64)")
    print("2. Ввести hex строку вручную")
    print("3. Ввести base64 строку вручную")
    
    choice = input("Ваш выбор (1-3): ").strip()
    
    auth_key = None
    
    if choice == "1":
        auth_key_file = input("Путь к файлу с Auth Key: ").strip()
        if not os.path.exists(auth_key_file):
            print(f"❌ Файл не найден: {auth_key_file}")
            return
        
        with open(auth_key_file, 'rb') as f:
            auth_key_data = f.read()
        
        # Определяем формат
        if len(auth_key_data) == 256:
            auth_key = auth_key_data
        else:
            try:
                # Пробуем hex
                auth_key = bytes.fromhex(auth_key_data.decode('utf-8').strip())
            except:
                try:
                    # Пробуем base64
                    import base64
                    auth_key = base64.b64decode(auth_key_data)
                except:
                    print("❌ Не удалось определить формат Auth Key")
                    return
    
    elif choice == "2":
        hex_string = input("Введите Auth Key (hex строка, 512 символов): ").strip()
        try:
            auth_key = bytes.fromhex(hex_string)
        except Exception as e:
            print(f"❌ Ошибка при парсинге hex: {e}")
            return
    
    elif choice == "3":
        base64_string = input("Введите Auth Key (base64 строка): ").strip()
        try:
            import base64
            auth_key = base64.b64decode(base64_string)
        except Exception as e:
            print(f"❌ Ошибка при парсинге base64: {e}")
            return
    
    else:
        print("❌ Неверный выбор!")
        return
    
    if not auth_key or len(auth_key) != 256:
        print(f"❌ Неверный размер Auth Key: {len(auth_key)} байт (ожидается 256)")
        return
    
    # Выполняем конвертацию
    await convert_tdata_to_string_session("", auth_key, api_id, api_hash, dc_id)


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Конвертация TData + Auth Key в String Session для Telethon                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

📋 Что нужно для конвертации:
   1. Auth Key (256 байт) - в любом формате (бинарный, hex, base64)
   2. API ID - можно получить на https://my.telegram.org/apps
   3. API Hash - можно получить на https://my.telegram.org/apps
   4. DC ID (опционально) - обычно 2 для Европы

💡 Форматы Auth Key:
   - Бинарный файл: 256 байт
   - Hex строка: 512 символов (256 байт в hex)
   - Base64 строка: ~344 символа

⚠️  Важно:
   - Auth Key должен быть валидным и не истекшим
   - Аккаунт должен быть активным
   - DC ID должен соответствовать региону аккаунта

""")
    
    asyncio.run(interactive_conversion())


