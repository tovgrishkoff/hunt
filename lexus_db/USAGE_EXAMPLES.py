#!/usr/bin/env python3
"""
Примеры использования Lexus DB Manager
"""
import asyncio
from datetime import datetime, timedelta
from lexus_db.session import AsyncSessionLocal, init_db
from lexus_db.db_manager import DbManager


async def example_get_ready_groups():
    """Пример: Получение групп, готовых для постинга"""
    async with AsyncSessionLocal() as session:
        db_manager = DbManager(session)
        
        # Получить группы, готовые для постинга
        ready_groups = await db_manager.get_groups_ready_for_posting(
            niche='ukraine_cars',
            limit=50
        )
        
        print(f"✅ Found {len(ready_groups)} groups ready for posting")
        
        for group in ready_groups:
            account = group.assigned_account
            print(f"\nGroup: {group.link}")
            print(f"  Account: {account.session_name}")
            print(f"  Warm-up finished: {group.is_warmup_finished()}")
            print(f"  Daily posts in group: {group.daily_posts_in_group}/2")
            print(f"  Account daily posts: {account.daily_posts_count}/20")
            print(f"  Account status: {account.status}")


async def example_assign_group():
    """Пример: Привязка группы к аккаунту после вступления"""
    async with AsyncSessionLocal() as session:
        db_manager = DbManager(session)
        
        # Получаем аккаунт по session_name
        account = await db_manager.get_account_by_session_name('promotion_dao_bro')
        if not account:
            print("❌ Account not found")
            return
        
        # Привязываем группу к аккаунту
        success = await db_manager.assign_group(
            group_link='@autobazar_com_ua',
            account_id=account.id,
            joined_at=datetime.utcnow()
        )
        
        if success:
            print("✅ Group assigned successfully")
        else:
            print("❌ Failed to assign group")


async def example_record_post():
    """Пример: Запись поста в историю"""
    async with AsyncSessionLocal() as session:
        db_manager = DbManager(session)
        
        # Получаем аккаунт и группу
        account = await db_manager.get_account_by_session_name('promotion_dao_bro')
        target = await db_manager.get_target_by_link('@autobazar_com_ua')
        
        if not account or not target:
            print("❌ Account or target not found")
            return
        
        # Записываем успешный пост
        await db_manager.record_post(
            account_id=account.id,
            target_id=target.id,
            message_content="Продается Lexus IS 250, 2015 год...",
            photo_path="/app/lexus_assets/lexus_variant_1.jpg",
            status='success'
        )
        
        print("✅ Post recorded successfully")


async def example_flood_wait():
    """Пример: Обработка FloodWait"""
    async with AsyncSessionLocal() as session:
        db_manager = DbManager(session)
        
        account = await db_manager.get_account_by_session_name('promotion_dao_bro')
        if not account:
            print("❌ Account not found")
            return
        
        # Устанавливаем FloodWait на 1 час
        wait_until = datetime.utcnow() + timedelta(hours=1)
        await db_manager.set_account_flood_wait(account.id, wait_until)
        print(f"✅ FloodWait set until {wait_until}")
        
        # Через час очищаем FloodWait
        # await db_manager.clear_account_flood_wait(account.id)
        # print("✅ FloodWait cleared")


async def example_account_stats():
    """Пример: Получение статистики аккаунта"""
    async with AsyncSessionLocal() as session:
        db_manager = DbManager(session)
        
        account = await db_manager.get_account_by_session_name('promotion_dao_bro')
        if not account:
            print("❌ Account not found")
            return
        
        stats = await db_manager.get_account_stats(account.id)
        
        print("📊 Account Statistics:")
        print(f"  Session name: {stats['session_name']}")
        print(f"  Status: {stats['status']}")
        print(f"  Daily posts: {stats['daily_posts_count']}/20")
        print(f"  Groups assigned: {stats['groups_count']}")
        print(f"  Posts today: {stats['posts_today']}")
        print(f"  Next allowed action: {stats['next_allowed_action_time']}")


async def main():
    """Запуск всех примеров"""
    print("=" * 80)
    print("LEXUS DB USAGE EXAMPLES")
    print("=" * 80)
    
    # Инициализируем БД (создаем таблицы)
    print("\n1. Initializing database...")
    try:
        await init_db()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        return
    
    # Запускаем примеры (закомментированы, чтобы не выполнять реальные операции)
    print("\n2. Example: Get ready groups")
    # await example_get_ready_groups()
    
    print("\n3. Example: Assign group")
    # await example_assign_group()
    
    print("\n4. Example: Record post")
    # await example_record_post()
    
    print("\n5. Example: FloodWait")
    # await example_flood_wait()
    
    print("\n6. Example: Account stats")
    # await example_account_stats()
    
    print("\n✅ Examples completed (operations are commented out)")


if __name__ == "__main__":
    asyncio.run(main())
