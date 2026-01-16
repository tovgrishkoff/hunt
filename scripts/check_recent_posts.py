#!/usr/bin/env python3
"""
Скрипт для проверки постов за последние N часов
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy import and_

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database.session import SessionLocal, init_db
from shared.database.models import Post, Account, Group
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_recent_posts(hours: int = 9):
    """
    Получить посты за последние N часов
    
    Args:
        hours: Количество часов для проверки
    """
    try:
        init_db()
        db = SessionLocal()
        
        try:
            # Вычисляем время начала периода
            now = datetime.utcnow()
            start_time = now - timedelta(hours=hours)
            
            logger.info(f"🔍 Поиск постов за последние {hours} часов")
            logger.info(f"   Время начала: {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            logger.info(f"   Текущее время: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            logger.info("-" * 80)
            
            # Запрос постов за указанный период
            posts = db.query(Post).join(Account).join(Group).filter(
                and_(
                    Post.sent_at >= start_time,
                    Post.sent_at <= now,
                    Post.success == True
                )
            ).order_by(Post.sent_at.desc()).all()
            
            if not posts:
                logger.info(f"❌ Постов за последние {hours} часов не найдено")
                return
            
            logger.info(f"✅ Найдено постов: {len(posts)}")
            logger.info("=" * 80)
            
            # Группируем по аккаунтам
            posts_by_account = {}
            for post in posts:
                account_name = post.account.session_name if post.account else "Unknown"
                if account_name not in posts_by_account:
                    posts_by_account[account_name] = []
                posts_by_account[account_name].append(post)
            
            # Выводим статистику по аккаунтам
            logger.info("\n📊 Статистика по аккаунтам:")
            for account_name, account_posts in sorted(posts_by_account.items(), 
                                                      key=lambda x: len(x[1]), 
                                                      reverse=True):
                logger.info(f"   {account_name}: {len(account_posts)} постов")
            
            logger.info("\n" + "=" * 80)
            logger.info("📝 Детальный список постов:\n")
            
            # Выводим детальную информацию
            for i, post in enumerate(posts, 1):
                # Время в UTC и локальное (киевское)
                utc_time = post.sent_at
                kyiv_time = utc_time + timedelta(hours=2)  # UTC+2 для Киева
                
                group_name = post.group.username if post.group else "Unknown"
                account_name = post.account.session_name if post.account else "Unknown"
                message_preview = (post.message_text[:60] + "...") if post.message_text and len(post.message_text) > 60 else (post.message_text or "Нет текста")
                
                logger.info(f"{i}. [{kyiv_time.strftime('%H:%M:%S')} КИЕВ] "
                          f"@{group_name} | {account_name}")
                logger.info(f"   {message_preview}")
                logger.info("")
            
            logger.info("=" * 80)
            logger.info(f"✅ Всего постов за последние {hours} часов: {len(posts)}")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Ошибка при получении постов: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    hours = 9
    if len(sys.argv) > 1:
        try:
            hours = int(sys.argv[1])
        except ValueError:
            logger.error(f"Неверный формат количества часов: {sys.argv[1]}")
            sys.exit(1)
    
    get_recent_posts(hours)
