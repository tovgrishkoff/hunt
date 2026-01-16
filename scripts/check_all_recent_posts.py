#!/usr/bin/env python3
"""
Скрипт для проверки всех недавних постов
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy import and_, desc

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


def check_all_recent_posts():
    """Проверить все недавние посты"""
    try:
        init_db()
        db = SessionLocal()
        
        try:
            now = datetime.utcnow()
            logger.info(f"Текущее время UTC: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"Текущее время КИЕВ: {(now + timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("-" * 80)
            
            # Получаем последние 100 постов
            posts = db.query(Post).join(Account).join(Group).filter(
                Post.success == True
            ).order_by(desc(Post.sent_at)).limit(100).all()
            
            if not posts:
                logger.info("❌ Постов в базе данных не найдено")
                return
            
            logger.info(f"✅ Найдено постов (последние 100): {len(posts)}")
            logger.info("=" * 80)
            
            # Группируем по датам
            posts_by_date = {}
            for post in posts:
                kyiv_time = post.sent_at + timedelta(hours=2)
                date_key = kyiv_time.strftime('%Y-%m-%d')
                if date_key not in posts_by_date:
                    posts_by_date[date_key] = []
                posts_by_date[date_key].append(post)
            
            # Выводим по датам
            for date_key in sorted(posts_by_date.keys(), reverse=True):
                date_posts = posts_by_date[date_key]
                logger.info(f"\n📅 {date_key} ({len(date_posts)} постов)")
                logger.info("-" * 80)
                
                # Группируем по аккаунтам
                posts_by_account = {}
                for post in date_posts:
                    account_name = post.account.session_name if post.account else "Unknown"
                    if account_name not in posts_by_account:
                        posts_by_account[account_name] = []
                    posts_by_account[account_name].append(post)
                
                # Выводим статистику по аккаунтам
                logger.info("   Статистика по аккаунтам:")
                for account_name, account_posts in sorted(posts_by_account.items(), 
                                                          key=lambda x: len(x[1]), 
                                                          reverse=True):
                    logger.info(f"      {account_name}: {len(account_posts)} постов")
                
                # Выводим первые 20 постов за этот день
                logger.info("\n   Последние посты:")
                for i, post in enumerate(date_posts[:20], 1):
                    kyiv_time = post.sent_at + timedelta(hours=2)
                    group_name = post.group.username if post.group else "Unknown"
                    account_name = post.account.session_name if post.account else "Unknown"
                    message_preview = (post.message_text[:50] + "...") if post.message_text and len(post.message_text) > 50 else (post.message_text or "Нет текста")
                    
                    logger.info(f"   {i}. [{kyiv_time.strftime('%H:%M:%S')}] "
                              f"@{group_name} | {account_name}")
                    logger.info(f"      {message_preview}")
                
                if len(date_posts) > 20:
                    logger.info(f"   ... и еще {len(date_posts) - 20} постов")
            
            # Проверяем посты за последние 9 часов
            logger.info("\n" + "=" * 80)
            logger.info("🔍 Проверка постов за последние 9 часов:")
            start_time = now - timedelta(hours=9)
            recent_posts = [p for p in posts if p.sent_at >= start_time]
            
            if recent_posts:
                logger.info(f"✅ Найдено {len(recent_posts)} постов за последние 9 часов")
                for post in recent_posts:
                    kyiv_time = post.sent_at + timedelta(hours=2)
                    group_name = post.group.username if post.group else "Unknown"
                    account_name = post.account.session_name if post.account else "Unknown"
                    logger.info(f"   [{kyiv_time.strftime('%H:%M:%S')}] @{group_name} | {account_name}")
            else:
                logger.info("❌ Постов за последние 9 часов не найдено")
                if posts:
                    last_post = posts[0]
                    last_post_kyiv = last_post.sent_at + timedelta(hours=2)
                    hours_ago = (now - last_post.sent_at).total_seconds() / 3600
                    logger.info(f"   Последний пост был: {last_post_kyiv.strftime('%Y-%m-%d %H:%M:%S')} КИЕВ")
                    logger.info(f"   Прошло часов: {hours_ago:.1f}")
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_all_recent_posts()
