import asyncio
import json
import logging
from telethon import TelegramClient

class QuickGroupChecker:
    def __init__(self):
        self.setup_logging()
        self.accounts = []
        
    def setup_logging(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def load_accounts(self):
        """Загрузка конфигурации аккаунтов"""
        try:
            with open('accounts_config.json', 'r', encoding='utf-8') as f:
                self.accounts = json.load(f)
            self.logger.info(f"Loaded {len(self.accounts)} accounts")
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return
    
    async def check_targets(self):
        """Быстрая проверка целей из targets.txt"""
        self.logger.info("🔍 Quick check of targets...")
        
        # Читаем targets.txt
        try:
            with open('targets.txt', 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
        except FileNotFoundError:
            self.logger.error("targets.txt not found")
            return
        
        self.logger.info(f"Found {len(lines)} targets to check")
        
        # Используем первый аккаунт для проверки
        account = self.accounts[0]
        client = TelegramClient(
            f"sessions/{account['session_name']}", 
            account['api_id'], 
            account['api_hash']
        )
        
        try:
            await client.start()
            self.logger.info(f"Using {account['session_name']} for checking")
            
            accessible_groups = []
            failed_groups = []
            
            for i, target in enumerate(lines, 1):
                try:
                    self.logger.info(f"Checking {i}/{len(lines)}: {target}")
                    
                    # Пробуем получить сущность
                    entity = await client.get_entity(target)
                    
                    # Проверяем права на отправку
                    try:
                        permissions = await client.get_permissions(entity)
                        can_send = permissions.send_messages if permissions else False
                    except:
                        can_send = False
                    
                    title = getattr(entity, 'title', 'Unknown')
                    members_count = getattr(entity, 'participants_count', 'Unknown')
                    
                    if can_send:
                        accessible_groups.append(target)
                        self.logger.info(f"✅ {target}: {title} ({members_count} members) - CAN SEND")
                    else:
                        self.logger.warning(f"⚠️ {target}: {title} ({members_count} members) - CANNOT SEND")
                        
                except Exception as e:
                    failed_groups.append(target)
                    self.logger.error(f"❌ {target}: {str(e)[:100]}...")
                
                # Небольшая пауза между проверками
                await asyncio.sleep(1)
            
            # Сохраняем результаты
            with open('accessible_groups.txt', 'w', encoding='utf-8') as f:
                for group in accessible_groups:
                    f.write(group + '\n')
            
            self.logger.info(f"\n📊 Results:")
            self.logger.info(f"✅ Accessible groups: {len(accessible_groups)}")
            self.logger.info(f"❌ Failed groups: {len(failed_groups)}")
            self.logger.info(f"📁 Accessible groups saved to accessible_groups.txt")
            
            return accessible_groups
            
        finally:
            await client.disconnect()

async def main():
    checker = QuickGroupChecker()
    checker.load_accounts()
    await checker.check_targets()

if __name__ == "__main__":
    asyncio.run(main())
