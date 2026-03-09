#!/usr/bin/env python3
"""
Сервис партизанского PR: диалоги в группах (вопрос → рекомендация → поддержка).
Пиар @marisha_lovephoto и других из config/bali_conversations.json.
"""
import asyncio
import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
logging.getLogger("telethon").setLevel(logging.WARNING)

from shared.telegram.client_manager import TelegramClientManager
from shared.database.session import SessionLocal

# Модуль из этой же директории
import importlib.util
runner_spec = importlib.util.spec_from_file_location(
    "conversation_runner",
    Path(__file__).parent / "conversation_runner.py",
)
runner_module = importlib.util.module_from_spec(runner_spec)
runner_spec.loader.exec_module(runner_module)
ConversationPRRunner = runner_module.ConversationPRRunner

_handlers = [logging.StreamHandler()]
_log_dir = Path("/app/logs")
if _log_dir.exists():
    _handlers.append(logging.FileHandler(_log_dir / "conversation_pr.log"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", handlers=_handlers)
logger = logging.getLogger(__name__)

INTERVAL_HOURS = int(os.getenv("CONVERSATION_PR_INTERVAL_HOURS", "12"))


class ConversationPRService:
    """Сервис диалогов в группах."""

    def __init__(self):
        self.client_manager = TelegramClientManager()
        self.runner = None

    async def initialize(self):
        """Загрузка аккаунтов из БД (Bali)."""
        db = SessionLocal()
        try:
            exclude_lexus = os.getenv("EXCLUDE_LEXUS_ACCOUNTS", "true").lower() in ("1", "true", "yes")
            await self.client_manager.load_accounts_from_db(db, exclude_lexus_accounts=exclude_lexus)
            logger.info(f"✅ Loaded {len(self.client_manager.clients)} accounts")
        except Exception as e:
            logger.error(f"❌ Failed to load accounts: {e}")
            raise
        finally:
            db.close()
        self.runner = ConversationPRRunner(self.client_manager)
        logger.info("✅ Conversation PR Service initialized")

    async def run_cycle(self):
        """Один цикл: до N диалогов в группах."""
        logger.info("=" * 80)
        logger.info("💬 CONVERSATION PR CYCLE - диалоги в группах (@marisha_lovephoto)")
        logger.info("=" * 80)
        try:
            result = await self.runner.run_cycle()
            logger.info(f"✅ Cycle done: sent={result['sent']}, skipped={result['skipped']}")
            return result
        except Exception as e:
            logger.error(f"❌ Error in cycle: {e}", exc_info=True)
            return {"sent": 0, "skipped": 0}

    async def run(self):
        await self.initialize()
        logger.info("=" * 80)
        logger.info("🚀 CONVERSATION PR SERVICE")
        logger.info(f"⏰ Interval: {INTERVAL_HOURS} hours")
        logger.info("=" * 80)
        while True:
            try:
                await self.run_cycle()
                wait_seconds = INTERVAL_HOURS * 3600
                logger.info(f"😴 Next cycle in {INTERVAL_HOURS} hours")
                await asyncio.sleep(wait_seconds)
            except KeyboardInterrupt:
                logger.info("🛑 Shutting down...")
                break
            except Exception as e:
                logger.error(f"❌ Error: {e}", exc_info=True)
                await asyncio.sleep(600)


async def main():
    service = ConversationPRService()
    try:
        await service.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"❌ Fatal: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
