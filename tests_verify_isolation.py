import argparse
import asyncio
from datetime import datetime
import os
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import create_async_engine


async def verify_isolation(env_file: str) -> None:
    """
    Загрузить переменные окружения из указанного файла, подключиться к БД
    и создать / прочитать тестовую запись, чтобы проверить изоляцию баз.
    """
    if not os.path.exists(env_file):
        raise FileNotFoundError(f"Env file not found: {env_file}")

    # Загружаем переменные окружения ДО импорта get_database_url
    load_dotenv(env_file, override=True)

    from lexus_db.session import get_database_url

    database_url = get_database_url()
    url_obj = make_url(database_url)

    print(f"Using database URL: {database_url}")
    print(f"Connected to database: {url_obj.database}")

    engine = create_async_engine(database_url, echo=False, future=True)

    marker = f"isolation-test-{datetime.utcnow().isoformat()}-{uuid4()}"

    async with engine.begin() as conn:
        # Создаем простую техническую таблицу, если её ещё нет
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS isolation_tests (
                    id SERIAL PRIMARY KEY,
                    marker TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
        )

        # Вставляем тестовую запись
        result = await conn.execute(
            text(
                """
                INSERT INTO isolation_tests (marker)
                VALUES (:marker)
                RETURNING id, marker, created_at
                """
            ),
            {"marker": marker},
        )
        inserted_row = result.fetchone()

        # Читаем обратно ту же запись по маркеру
        result = await conn.execute(
            text(
                """
                SELECT id, marker, created_at
                FROM isolation_tests
                WHERE marker = :marker
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"marker": marker},
        )
        fetched_row = result.fetchone()

    await engine.dispose()

    print("Inserted row:", dict(inserted_row._mapping) if inserted_row else None)
    print("Fetched row: ", dict(fetched_row._mapping) if fetched_row else None)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that different env files point to isolated databases by "
            "creating and reading a test record."
        )
    )
    parser.add_argument(
        "--env-file",
        required=True,
        help="Path to .env file with POSTGRES_* / DATABASE_URL settings",
    )
    args = parser.parse_args()

    asyncio.run(verify_isolation(args.env_file))


if __name__ == "__main__":
    main()

