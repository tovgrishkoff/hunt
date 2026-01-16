#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Система ежедневной отправки объявлений с фото на доску объявлений
"""

import asyncio
import json
import logging
import os
import aiohttp
import tempfile
from pathlib import Path
from datetime import datetime, time as dtime
from telethon import TelegramClient
from telethon.errors import RPCError
import pytz


class DailyAnnouncementSystem:
    def __init__(self, admin_id: int = 210147380):
        self.accounts = []
        self.clients = {}
        self.config = {}
        self.last_sent_date = None
        self.setup_logging()
        
    def setup_logging(self):
        """Настройка логирования"""
        logs_dir = Path("logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / "daily_announcement.log"

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_config(self, config_file='announcement_config.json'):
        """Загрузка конфигурации объявлений"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.logger.info(f"✅ Загружена конфигурация из {config_file}")
            return True
        except FileNotFoundError:
            self.logger.error(f"❌ Файл конфигурации {config_file} не найден")
            self.create_default_config(config_file)
            return False
        except json.JSONDecodeError as e:
            self.logger.error(f"❌ Ошибка парсинга JSON в {config_file}: {e}")
            return False
    
    def create_default_config(self, config_file):
        """Создание конфигурации по умолчанию"""
        default_config = {
            "target_group": "@obyavlenia_bali",  # Доска объявлений
            "account_name": "promotion_alex_ever",  # Какой аккаунт использовать
            "photo_path": "announcement_photo.jpg",  # Путь к фото
            "message_text": "📢 Ваше объявление здесь\n\nПодробности...",
            "send_time": "09:00",  # Время отправки (формат HH:MM)
            "timezone": "Asia/Jakarta"  # Часовой пояс
        }
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
            
        self.logger.info(f"✅ Создан файл конфигурации по умолчанию: {config_file}")
        self.config = default_config
    
    def load_accounts(self, config_file='accounts_config.json'):
        """Загрузка конфигурации аккаунтов"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.accounts = json.load(f)
            self.logger.info(f"✅ Загружено {len(self.accounts)} аккаунтов")
            return True
        except FileNotFoundError:
            self.logger.error(f"❌ Файл {config_file} не найден")
            return False
        except json.JSONDecodeError as e:
            self.logger.error(f"❌ Ошибка парсинга JSON: {e}")
            return False
    
    async def initialize_client(self, account_name: str):
        """Инициализация клиента для указанного аккаунта"""
        account = next((acc for acc in self.accounts if acc['session_name'] == account_name), None)
        if not account:
            self.logger.error(f"❌ Аккаунт {account_name} не найден в конфигурации")
            return False
        
        try:
            self.logger.info(f"🔄 Инициализация {account_name}...")
            
            api_id = int(account['api_id'])
            string_session = account.get('string_session')
            
            if string_session:
                from telethon.sessions import StringSession
                client = TelegramClient(StringSession(string_session), api_id, account['api_hash'])
            else:
                client = TelegramClient(f"sessions/{account_name}", api_id, account['api_hash'])
            
            await client.connect()
            self.logger.info(f"  ✅ Подключен {account_name}")
            
            if await client.is_user_authorized():
                self.clients[account_name] = client
                self.logger.info(f"✅ Клиент {account_name} готов")
                return True
            else:
                self.logger.error(f"❌ Клиент {account_name} не авторизован")
                await client.disconnect()
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка инициализации {account_name}: {e}")
            return False
    
    async def resolve_target(self, client: TelegramClient, target: str):
        """Разрешение цели: username/link/ID -> entity"""
        try:
            if target.isdigit():
                target_id = int(target)
                return await client.get_entity(target_id)
            return await client.get_entity(target)
        except Exception as e:
            self.logger.error(f"❌ Не удалось найти {target}: {e}")
            return None
    
    def convert_google_drive_url(self, url: str) -> str:
        """Преобразование Google Drive ссылки в прямую ссылку для скачивания"""
        # Если это уже прямая ссылка для скачивания
        if 'drive.google.com/uc?export=download' in url:
            return url
        
        # Если это обычная ссылка Google Drive
        if 'drive.google.com/file/d/' in url:
            file_id = url.split('/file/d/')[1].split('/')[0]
            return f"https://drive.google.com/uc?export=download&id={file_id}"
        
        # Если это ссылка вида drive.google.com/open?id=...
        if 'drive.google.com/open?id=' in url:
            file_id = url.split('id=')[1].split('&')[0]
            return f"https://drive.google.com/uc?export=download&id={file_id}"
        
        # Если это уже прямая ссылка или другой URL
        return url
    
    async def download_file(self, url: str) -> str:
        """Скачивание файла по URL во временный файл"""
        try:
            # Преобразуем Google Drive ссылку если нужно
            download_url = self.convert_google_drive_url(url)
            
            self.logger.info(f"📥 Скачивание файла с {download_url}...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(download_url, allow_redirects=True) as response:
                    if response.status != 200:
                        raise Exception(f"Ошибка загрузки: HTTP {response.status}")
                    
                    # Создаем временный файл
                    suffix = Path(url).suffix or '.jpg'
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                    
                    # Скачиваем содержимое
                    content = await response.read()
                    temp_file.write(content)
                    temp_file.close()
                    
                    self.logger.info(f"✅ Файл скачан: {temp_file.name} ({len(content)} байт)")
                    return temp_file.name
                    
        except Exception as e:
            self.logger.error(f"❌ Ошибка скачивания файла: {e}")
            raise
    
    async def send_announcement(self, target_group: str, dry_run: bool = False):
        """Отправка объявления с фото (поддержка альбома) с резервными аккаунтами"""
        primary_account = self.config.get('account_name')
        fallback_accounts = self.config.get('fallback_accounts', [])
        photo_path_or_url = self.config.get('photo_path')
        message_text = self.config.get('message_text', '')

        # Формируем список аккаунтов в порядке приоритета
        account_candidates = []
        if primary_account:
            account_candidates.append(primary_account)
        for acc in fallback_accounts:
            if acc not in account_candidates:
                account_candidates.append(acc)

        if not account_candidates:
            self.logger.error("❌ Не указаны аккаунты для отправки (account_name / fallback_accounts)")
            return False
        
        # Поддержка нескольких фото (список или строка)
        if isinstance(photo_path_or_url, str):
            photo_list = [photo_path_or_url]
        elif isinstance(photo_path_or_url, list):
            photo_list = photo_path_or_url
        else:
            self.logger.error("❌ Неверный формат photo_path (должна быть строка или список)")
            return False
        
        # Пытаемся отправить через основной и резервные аккаунты
        for account_name in account_candidates:
            client = self.clients.get(account_name)
            if not client:
                self.logger.warning(f"⚠️ Клиент {account_name} не инициализирован, пробуем следующий аккаунт")
                continue

            temp_files = []

            try:
                photo_files = []

                for photo_item in photo_list:
                    # Определяем, это URL или локальный путь
                    is_url = photo_item.startswith('http://') or photo_item.startswith('https://')

                    if is_url:
                        # Скачиваем файл по URL
                        temp_file_path = await self.download_file(photo_item)
                        temp_files.append(temp_file_path)
                        photo_files.append(temp_file_path)
                    else:
                        # Используем локальный файл
                        photo_file = Path(photo_item)
                        if not photo_file.exists():
                            self.logger.error(f"❌ Файл фото не найден: {photo_item}")
                            continue
                        photo_files.append(str(photo_file))

                if not photo_files:
                    self.logger.error("❌ Не удалось загрузить ни одного фото")
                    return False

                # Разрешаем группу
                entity = await self.resolve_target(client, target_group)
                if entity is None:
                    self.logger.warning(f"⚠️ Не удалось разрешить цель {target_group} через {account_name}, пробуем следующий аккаунт")
                    continue

                if dry_run:
                    self.logger.info(f"[DRY-RUN] Отправил бы объявление в {target_group} через {account_name}")
                    self.logger.info(f"[DRY-RUN] Фото ({len(photo_files)} шт.): {photo_list}")
                    self.logger.info(f"[DRY-RUN] Текст: {message_text[:200]}...")
                    return True

                # Telegram ограничение: 1024 символа для подписи к медиа
                MAX_CAPTION_LENGTH = 1024

                # Если текст слишком длинный, обрезаем его
                if len(message_text) > MAX_CAPTION_LENGTH:
                    # Берем первые 1020 символов и добавляем "..."
                    short_caption = message_text[:1020] + "..."
                    remaining_text = message_text[1020:]
                else:
                    short_caption = message_text
                    remaining_text = None

                try:
                    # Если одно фото - отправляем с подписью
                    if len(photo_files) == 1:
                        await client.send_file(
                            entity,
                            photo_files[0],
                            caption=short_caption
                        )
                    else:
                        # Если несколько фото - отправляем альбом
                        # Первое фото с подписью, остальные без
                        files_to_send = [photo_files[0]]
                        captions = [short_caption]

                        for photo_file in photo_files[1:]:
                            files_to_send.append(photo_file)
                            captions.append("")  # Пустые подписи для остальных фото

                        await client.send_file(
                            entity,
                            files_to_send,
                            caption=captions
                        )

                    # Если остался текст - отправляем его отдельным сообщением
                    if remaining_text:
                        await asyncio.sleep(1)  # Небольшая задержка между сообщениями
                        await client.send_message(entity, remaining_text)
                        self.logger.info(f"📝 Дополнительный текст отправлен отдельным сообщением")

                    self.logger.info(f"✅ Объявление отправлено в {target_group} через {account_name} ({len(photo_files)} фото)")
                    # last_sent_date будет сохранен в планировщике
                    return True

                except RPCError as e:
                    self.logger.error(f"❌ Ошибка отправки в {target_group} через {account_name}: {e}")
                    # Пробуем следующий аккаунт
                    continue
                except Exception as e:
                    self.logger.error(f"❌ Неожиданная ошибка при отправке в {target_group} через {account_name}: {e}")
                    # Пробуем следующий аккаунт
                    continue

            finally:
                # Удаляем временные файлы если они были скачаны
                for temp_file_path in temp_files:
                    if os.path.exists(temp_file_path):
                        try:
                            os.unlink(temp_file_path)
                            self.logger.info(f"🗑️ Временный файл удален: {temp_file_path}")
                        except Exception as e:
                            self.logger.warning(f"⚠️ Не удалось удалить временный файл: {e}")

        self.logger.error(f"❌ Не удалось отправить объявление в {target_group} ни через один доступный аккаунт")
        return False
    
    async def run_daily_scheduler(self, dry_run: bool = False):
        """Запуск планировщика для нескольких групп с разными интервалами"""
        timezone_str = self.config.get('timezone', 'Asia/Jakarta')
        target_groups = self.config.get('target_groups', [])
        
        # Поддержка старого формата (для обратной совместимости)
        if not target_groups:
            target_group = self.config.get('target_group')
            interval_hours = self.config.get('interval_hours', 36)
            if target_group:
                target_groups = [{"group": target_group, "interval_hours": interval_hours}]
        
        if not target_groups:
            self.logger.error("❌ Не указаны группы для отправки")
            return
        
        try:
            tz = pytz.timezone(timezone_str)
        except Exception as e:
            self.logger.error(f"❌ Ошибка парсинга часового пояса: {e}")
            return
        
        self.logger.info(f"📅 Планировщик запущен для {len(target_groups)} групп ({timezone_str})")
        for tg in target_groups:
            self.logger.info(f"  • {tg['group']}: каждые {tg['interval_hours']} часов")
        
        # Загружаем даты последних отправок из файла (если есть)
        last_sent_file = Path("last_sent_announcement.json")
        last_sent_times = {}
        if last_sent_file.exists():
            try:
                with open(last_sent_file, 'r') as f:
                    last_sent_data = json.load(f)
                    for group_info in target_groups:
                        group = group_info['group']
                        last_sent_str = last_sent_data.get(group)
                        if last_sent_str:
                            last_sent_times[group] = datetime.fromisoformat(last_sent_str)
                            self.logger.info(f"📅 Последняя отправка в {group}: {last_sent_times[group].strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception as e:
                self.logger.warning(f"⚠️ Не удалось загрузить даты последних отправок: {e}")
        
        from datetime import timedelta
        
        while True:
            now = datetime.now(tz)
            next_send_times = {}
            
            # Вычисляем время следующей отправки для каждой группы
            for group_info in target_groups:
                group = group_info['group']
                interval_hours = group_info['interval_hours']
                
                if group in last_sent_times:
                    # Если уже отправляли - следующая отправка через interval_hours
                    last_sent = last_sent_times[group]
                    if last_sent.tzinfo is None:
                        last_sent = tz.localize(last_sent)
                    else:
                        last_sent = last_sent.astimezone(tz)
                    
                    next_send = last_sent + timedelta(hours=interval_hours)
                else:
                    # Первая отправка - отправляем сразу
                    next_send = now
                
                # Если время уже прошло, отправляем сейчас
                if next_send <= now:
                    next_send = now
                
                next_send_times[group] = next_send
            
            # Находим ближайшую отправку
            next_group = min(next_send_times.items(), key=lambda x: x[1])
            next_group_name, next_send_time = next_group
            
            wait_seconds = max(1, int((next_send_time - now).total_seconds()))
            hours = wait_seconds // 3600
            minutes = (wait_seconds % 3600) // 60
            
            self.logger.info(f"⏰ Следующая отправка в {next_group_name}: {next_send_time.strftime('%Y-%m-%d %H:%M:%S')} (через {hours}ч {minutes}м)")
            
            await asyncio.sleep(wait_seconds)
            
            # Время отправки наступило
            self.logger.info(f"⏰ Время отправки наступило для {next_group_name}: {datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')}")
            success = await self.send_announcement(next_group_name, dry_run=dry_run)
            
            # Сохраняем время отправки
            if success and not dry_run:
                try:
                    # Загружаем существующие данные
                    if last_sent_file.exists():
                        with open(last_sent_file, 'r') as f:
                            last_sent_data = json.load(f)
                    else:
                        last_sent_data = {}
                    
                    # Обновляем время для этой группы
                    last_sent_data[next_group_name] = datetime.now(tz).isoformat()
                    last_sent_times[next_group_name] = datetime.now(tz)
                    
                    # Сохраняем
                    with open(last_sent_file, 'w') as f:
                        json.dump(last_sent_data, f, indent=2)
                except Exception as e:
                    self.logger.warning(f"⚠️ Не удалось сохранить дату отправки: {e}")
    
    async def run(self, dry_run: bool = False, send_now: bool = False):
        """Запуск системы"""
        self.logger.info("🚀 Запуск системы ежедневных объявлений...")
        
        # Загружаем конфигурацию
        if not self.load_config():
            self.logger.warning("⚠️ Используется конфигурация по умолчанию")
        
        # Загружаем аккаунты
        if not self.load_accounts():
            self.logger.error("❌ Не удалось загрузить аккаунты")
            return
        
        # Инициализируем основной и резервные аккаунты
        primary_account = self.config.get('account_name')
        fallback_accounts = self.config.get('fallback_accounts', [])

        if not primary_account:
            self.logger.error("❌ Не указан account_name в конфигурации")
            return

        account_candidates = [primary_account] + [
            acc for acc in fallback_accounts if acc != primary_account
        ]

        initialized_any = False
        for acc_name in account_candidates:
            if acc_name in self.clients:
                continue
            ok = await self.initialize_client(acc_name)
            if ok:
                initialized_any = True

        if not initialized_any:
            self.logger.error("❌ Не удалось инициализировать ни один аккаунт для объявлений")
            return
        
        if send_now:
            # Отправляем сразу во все группы
            target_groups = self.config.get('target_groups', [])
            if not target_groups:
                target_group = self.config.get('target_group')
                if target_group:
                    target_groups = [{"group": target_group}]
            
            if not target_groups:
                self.logger.error("❌ Не указаны группы для отправки")
                return
            
            self.logger.info(f"📤 Отправка объявления сейчас в {len(target_groups)} групп...")
            for group_info in target_groups:
                group = group_info['group']
                self.logger.info(f"📤 Отправка в {group}...")
                await self.send_announcement(group, dry_run=dry_run)
                await asyncio.sleep(2)  # Небольшая задержка между группами
        else:
            # Запускаем планировщик
            await self.run_daily_scheduler(dry_run=dry_run)


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Система ежедневных объявлений с фото')
    parser.add_argument('--dry-run', action='store_true', help='Тестовый режим (не отправлять)')
    parser.add_argument('--send-now', action='store_true', help='Отправить сейчас (один раз)')
    args = parser.parse_args()
    
    system = DailyAnnouncementSystem()
    await system.run(dry_run=args.dry_run, send_now=args.send_now)


if __name__ == "__main__":
    asyncio.run(main())

