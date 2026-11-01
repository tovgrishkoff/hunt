import asyncpg
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


def _parse_ts(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None

class Database:
    def __init__(self, dsn):
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(dsn=self.dsn)
        await self.ensure_conversion_schema()

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def add_message(self, category, sender_name, chat_title, message_text, message_link):
        async with self.pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO messages (category, sender_name, chat_title, message_text, message_link)
                VALUES ($1, $2, $3, $4, $5)
                ''',
                category, sender_name, chat_title, message_text, message_link
            )

    async def get_unprocessed_messages(self):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT id, category, sender_name, chat_title, message_text, message_link
                FROM messages
                WHERE is_processed = FALSE
                '''
            )
            return [dict(row) for row in rows]

    async def mark_message_as_processed(self, message_id):
        async with self.pool.acquire() as conn:
            await conn.execute(
                '''
                UPDATE messages
                SET is_processed = TRUE
                WHERE id = $1
                ''',
                message_id
            )

    async def ensure_conversion_schema(self):
        """Колонки для конверсии: триал, лиды, блокировка бота, напоминания."""
        if not self.pool:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                ALTER TABLE subscribers
                ADD COLUMN IF NOT EXISTS trial_leads_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS bot_blocked BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMP WITH TIME ZONE,
                ADD COLUMN IF NOT EXISTS trial_reminder_d2_sent BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS trial_reminder_d1_sent BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS trial_reminder_d0_sent BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS trial_zero_leads_reminder_sent BOOLEAN DEFAULT FALSE
                """
            )

    async def add_subscriber(self, user_id, categories):
        """Добавляет подписчика. Триал не стартует до выбора ≥1 ниши (start_trial_if_needed)."""
        async with self.pool.acquire() as conn:
            try:
                existing_user = await conn.fetchrow(
                    "SELECT user_id FROM subscribers WHERE user_id = $1",
                    user_id,
                )
                if existing_user:
                    await conn.execute(
                        """
                        UPDATE subscribers SET categories = $2, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = $1
                        """,
                        user_id,
                        json.dumps(categories),
                    )
                    logger.info(
                        f"✅ Обновлены категории для существующего пользователя {user_id}"
                    )
                else:
                    await conn.execute(
                        """
                        INSERT INTO subscribers (user_id, categories, countries, settings, trial_until)
                        VALUES ($1, $2, $3, $4, NULL)
                        """,
                        user_id,
                        json.dumps(categories),
                        json.dumps([]),
                        json.dumps({}),
                    )
                    logger.info(
                        f"✅ Новый пользователь {user_id} создан (триал после выбора ниш)"
                    )
                if categories:
                    await self.start_trial_if_needed(user_id, conn=conn)
            except Exception as e:
                logger.error(
                    f"❌ Ошибка при создании/обновлении пользователя {user_id}: {e}"
                )
                raise

    async def start_trial_if_needed(self, user_id: int, conn=None) -> bool:
        """Запускает триал при первом сохранении ≥1 ниши, если нет платной подписки."""
        from config import TRIAL_DAYS

        async def _run(c):
            row = await c.fetchrow(
                """
                SELECT subscription_active, subscription_until, trial_until, categories
                FROM subscribers WHERE user_id = $1
                """,
                user_id,
            )
            if not row:
                return False
            now = datetime.now(timezone.utc)
            sub_until = _parse_ts(row.get("subscription_until"))
            if row.get("subscription_active") is True and (
                sub_until is None or sub_until > now
            ):
                return False
            if row.get("trial_until") is not None:
                return False
            categories = json.loads(row["categories"]) if row["categories"] else []
            if not categories:
                return False
            trial_until = now + timedelta(days=TRIAL_DAYS)
            await c.execute(
                """
                UPDATE subscribers
                SET trial_until = $2, trial_started_at = $3, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = $1
                """,
                user_id,
                trial_until,
                now,
            )
            logger.info(
                f"🎁 Триал {TRIAL_DAYS} дн. для {user_id} до {trial_until.isoformat()}"
            )
            return True

        if conn:
            return await _run(conn)
        async with self.pool.acquire() as c:
            return await _run(c)

    async def get_subscription_status(self, user_id: int) -> Dict[str, Any]:
        """Единая логика: trial_until + subscription_active."""
        user = await self.get_user(user_id)
        now = datetime.now(timezone.utc)
        if not user:
            return {
                "exists": False,
                "subscription_active": False,
                "trial_active": False,
                "trial_not_started": True,
                "on_trial": False,
                "trial_days_left": None,
                "trial_leads_count": 0,
            }
        sub_until = _parse_ts(user.get("subscription_until"))
        trial_until = _parse_ts(user.get("trial_until"))
        subscription_active = user.get("subscription_active") is True and (
            sub_until is None or sub_until > now
        )
        trial_active = (
            not subscription_active
            and trial_until is not None
            and trial_until > now
        )
        trial_not_started = trial_until is None and not subscription_active
        days_left = None
        if trial_active and trial_until:
            days_left = max(0, (trial_until.date() - now.date()).days)
        leads = int(user.get("trial_leads_count") or 0)
        return {
            "exists": True,
            "subscription_active": subscription_active,
            "trial_active": trial_active,
            "trial_not_started": trial_not_started,
            "on_trial": trial_active,
            "trial_until": trial_until,
            "trial_days_left": days_left,
            "trial_leads_count": leads,
            "bot_blocked": bool(user.get("bot_blocked")),
        }

    async def has_active_subscription(self, user_id: int) -> bool:
        st = await self.get_subscription_status(user_id)
        return st["subscription_active"]

    async def increment_trial_leads_count(self, user_id: int, delta: int = 1):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE subscribers
                SET trial_leads_count = COALESCE(trial_leads_count, 0) + $2
                WHERE user_id = $1
                """,
                user_id,
                delta,
            )

    async def set_bot_blocked(self, user_id: int, blocked: bool = True):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE subscribers SET bot_blocked = $2 WHERE user_id = $1",
                user_id,
                blocked,
            )

    async def activate_subscription(
        self, user_id: int, days: int = 30, payment_ref: Optional[str] = None
    ):
        """Активация платной подписки в Postgres (Stars / менеджер)."""
        now = datetime.now(timezone.utc)
        until = now + timedelta(days=days)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id FROM subscribers WHERE user_id = $1", user_id
            )
            if not row:
                await conn.execute(
                    """
                    INSERT INTO subscribers (user_id, categories, subscription_active, subscription_until)
                    VALUES ($1, '[]', TRUE, $2)
                    """,
                    user_id,
                    until,
                )
            else:
                await conn.execute(
                    """
                    UPDATE subscribers
                    SET subscription_active = TRUE,
                        subscription_until = $2,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = $1
                    """,
                    user_id,
                    until,
                )
        logger.info(
            f"💳 Подписка активирована для {user_id} до {until.isoformat()} ref={payment_ref}"
        )

    async def get_subscribers_for_category(self, category):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT user_id, categories FROM subscribers
                '''
            )
            subscribers = []
            for row in rows:
                cats = json.loads(row['categories'])
                if category in cats:
                    subscribers.append(row['user_id'])
            return subscribers

    async def get_all_users(self) -> List[dict]:
        """Получение всех пользователей из базы данных"""
        try:
            async with self.pool.acquire() as conn:
                query = "SELECT * FROM subscribers"
                rows = await conn.fetch(query)
                users = [dict(row) for row in rows]
                logger.info(f"📊 Получено {len(users)} пользователей из базы данных")
                for user in users:
                    logger.info(f"👤 Пользователь {user['user_id']}: категории={user['categories']}")
                return users
        except Exception as e:
            logger.error(f"❌ Ошибка при получении пользователей: {e}")
            return []

    async def get_user(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM subscribers WHERE user_id = $1',
                user_id
            )
            return dict(row) if row else None

    async def get_user_settings(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT settings FROM subscribers WHERE user_id = $1',
                user_id
            )
            return json.loads(row['settings']) if row and row['settings'] else {}

    async def get_user_keywords(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT keywords FROM subscribers WHERE user_id = $1',
                user_id
            )
            return json.loads(row['keywords']) if row and row['keywords'] else {}

    async def get_user_niches(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT categories FROM subscribers WHERE user_id = $1',
                user_id
            )
            categories = json.loads(row['categories']) if row and row['categories'] else []
            logger.info(f"📋 Получены ниши пользователя {user_id}: {categories}")
            return categories

    async def get_subscribers_for_niche(self, niche: str, country: str = None) -> List[int]:
        """
        Получение списка подписчиков для конкретной ниши с опциональной фильтрацией по стране
        
        Args:
            niche: Название ниши
            country: Название страны (например, "Бали", "Таиланд") или None для всех стран
        
        Returns:
            Список user_id подписчиков (только с активной подпиской или действующим триалом)
        """
        try:
            async with self.pool.acquire() as conn:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                
                # Получаем всех подписчиков с их категориями, странами и статусом подписки
                rows = await conn.fetch(
                    """
                    SELECT user_id, categories, countries, subscription_active,
                           subscription_until, trial_until, bot_blocked
                    FROM subscribers
                    WHERE COALESCE(bot_blocked, FALSE) = FALSE
                    """
                )
                subscribers = []
                
                # Нормализуем искомую нишу
                niche_normalized = niche.lower()
                
                # Нормализуем страну для сравнения
                # Маппинг кириллических названий на латинские (как в базе данных)
                country_name_mapping = {
                    "бали": "bali",
                    "таиланд": "thailand",
                    "турция": "turkey",
                    "грузия": "georgia",
                    "вьетнам": "vietnam",
                    "дубай": "dubai",
                    "дубай / оаэ": "dubai",
                    "оаэ": "dubai",
                    "россия": "russia",
                    "армения": "armenia",
                    "сербия": "serbia",
                    "гоа": "goa",
                    "гоа / индия": "goa",
                    "индия": "goa",
                    "кейптаун": "cape_town",
                    "кейптаун / юар": "cape_town",
                    "юар": "cape_town",
                    "сша": "usa",
                    "usa": "usa",
                }
                if country:
                    country_lower = country.lower()
                    # Если страна в кириллице, маппим на латиницу
                    country_normalized = country_name_mapping.get(country_lower, country_lower)
                else:
                    country_normalized = None
                
                for row in rows:
                    # ВАЖНО: Проверяем статус подписки и триала ПЕРЕД проверкой ниш
                    subscription_active = row.get('subscription_active', False)
                    subscription_until = row.get('subscription_until')
                    trial_until = row.get('trial_until')
                    
                    # Пользователь должен иметь либо активную подписку, либо действующий триал
                    # Проверяем подписку: subscription_active = True И (безлимит ИЛИ не истекла)
                    has_active_subscription = subscription_active is True and (
                        subscription_until is None or subscription_until > now
                    )
                    has_active_trial = trial_until is not None and trial_until > now
                    
                    if not has_active_subscription and not has_active_trial:
                        # Пропускаем пользователей без активной подписки и с истекшим/отсутствующим триалом
                        continue
                    
                    categories = json.loads(row['categories']) if row['categories'] else []
                    # Проверяем каждую категорию в нижнем регистре
                    if any(cat.lower() == niche_normalized for cat in categories):
                        # ВАЖНО: Проверяем фильтрацию по странам пользователя
                        # Получаем страны пользователя
                        user_countries = row.get('countries')
                        user_countries_list = []
                        if user_countries:
                            # Парсим страны пользователя
                            if isinstance(user_countries, str):
                                try:
                                    user_countries_list = json.loads(user_countries)
                                except:
                                    user_countries_list = []
                            elif isinstance(user_countries, list):
                                user_countries_list = user_countries
                        
                        # Нормализуем страны пользователя для сравнения
                        user_countries_normalized = [c.lower() if isinstance(c, str) else str(c).lower() for c in user_countries_list]
                        
                        # Если пользователь ВЫБРАЛ страны (список не пустой), применяем строгую фильтрацию
                        if user_countries_normalized:
                            # Пользователь выбрал конкретные страны - отправляем ТОЛЬКО из этих стран
                            if country_normalized:
                                # Страна чата определена - проверяем, есть ли она в списке выбранных стран
                                if country_normalized not in user_countries_normalized:
                                    logger.info(f"🌍 Пользователь {row['user_id']} подписан на нишу '{niche}', но не подписан на страну '{country}' (его страны: {user_countries_list}), пропускаем")
                                    continue
                                else:
                                    logger.info(f"🌍 ✅ Пользователь {row['user_id']} подписан на нишу '{niche}' и страну '{country}'")
                            else:
                                # Страна чата НЕ определена, но пользователь выбрал конкретные страны
                                # НЕ отправляем - пользователь хочет получать только из выбранных стран
                                logger.info(f"🌍 Пользователь {row['user_id']} подписан на нишу '{niche}' и выбрал страны {user_countries_list}, но страна чата не определена - пропускаем")
                                continue
                        else:
                            # Пользователь НЕ выбрал страны - применяем обратную совместимость
                            # - Для админа: строгая фильтрация (не отправляем, если не выбрал страны)
                            # - Для обычных пользователей: отправляем все сообщения (обратная совместимость)
                            from config import ADMIN_CHAT_ID
                            is_admin = str(row['user_id']) == str(ADMIN_CHAT_ID)
                            if is_admin:
                                logger.info(f"🌍 Админ {row['user_id']} подписан на нишу '{niche}', но не выбрал страны (пропускаем - строгая фильтрация для админа)")
                                continue
                            else:
                                # Обычный пользователь без выбранных стран - отправляем все (обратная совместимость)
                                logger.info(f"🌍 Пользователь {row['user_id']} подписан на нишу '{niche}', но не выбрал страны (отправляем все - обратная совместимость)")
                        
                        subscribers.append(row['user_id'])
                        logger.info(f"✅ Пользователь {row['user_id']} подписан на нишу '{niche}' (найдено в категориях: {categories})")
                
                logger.info(f"📊 Найдено {len(subscribers)} подписчиков для ниши '{niche}'" + (f" и страны '{country}'" if country else ""))
                return subscribers
        except Exception as e:
            logger.error(f"❌ Ошибка при получении подписчиков для ниши {niche}: {e}")
            return []

    async def add_user_niche(self, user_id, niche):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT categories FROM subscribers WHERE user_id = $1', user_id)
            categories = json.loads(row['categories']) if row and row['categories'] else []
            # Нормализуем искомую нишу для сравнения
            niche_normalized = niche.lower()
            # Проверяем, есть ли уже такая ниша (без учета регистра)
            if not any(cat.lower() == niche_normalized for cat in categories):
                categories.append(niche)
                await conn.execute('UPDATE subscribers SET categories = $1 WHERE user_id = $2', json.dumps(categories), user_id)
                logger.info(f"✅ Добавлена ниша '{niche}' пользователю {user_id}")
            else:
                logger.info(f"ℹ️ Ниша '{niche}' уже есть у пользователя {user_id}")

    async def remove_user_niche(self, user_id, niche):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT categories FROM subscribers WHERE user_id = $1', user_id)
            categories = json.loads(row['categories']) if row and row['categories'] else []
            # Нормализуем искомую нишу для сравнения
            niche_normalized = niche.lower()
            # Удаляем ВСЕ варианты ниши (с разным регистром)
            original_length = len(categories)
            categories = [cat for cat in categories if cat.lower() != niche_normalized]
            
            if len(categories) < original_length:
                await conn.execute('UPDATE subscribers SET categories = $1 WHERE user_id = $2', json.dumps(categories), user_id)
                logger.info(f"✅ Удалена ниша '{niche}' у пользователя {user_id} (удалено {original_length - len(categories)} дубликатов)")
            else:
                logger.warning(f"⚠️ Ниша '{niche}' не найдена у пользователя {user_id} (категории: {categories})")

    async def clean_duplicate_niches(self, user_id):
        """Очищает дубликаты ниш у пользователя"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT categories FROM subscribers WHERE user_id = $1', user_id)
            categories = json.loads(row['categories']) if row and row['categories'] else []
            
            # Создаем словарь для отслеживания уникальных ниш (в нижнем регистре)
            unique_niches = {}
            for cat in categories:
                cat_lower = cat.lower()
                if cat_lower not in unique_niches:
                    unique_niches[cat_lower] = cat
            
            # Создаем новый список без дубликатов
            cleaned_categories = list(unique_niches.values())
            
            if len(cleaned_categories) != len(categories):
                await conn.execute('UPDATE subscribers SET categories = $1 WHERE user_id = $2', json.dumps(cleaned_categories), user_id)
                logger.info(f"🧹 Очищены дубликаты у пользователя {user_id}: было {len(categories)}, стало {len(cleaned_categories)}")
            
            return cleaned_categories

    async def get_all_subscribers(self):
        """Получение всех подписчиков с их категориями"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('SELECT user_id, categories FROM subscribers')
                subscribers = []
                for row in rows:
                    subscriber = {
                        'user_id': row['user_id'],
                        'categories': json.loads(row['categories']) if row['categories'] else []
                    }
                    subscribers.append(subscriber)
                return subscribers
        except Exception as e:
            print(f"Ошибка получения подписчиков: {e}")
            raise

    async def get_all_subscribers_with_niches(self):
        """Получение всех подписчиков с их нишами"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('SELECT user_id, categories FROM subscribers')
                subscribers = {}
                for row in rows:
                    categories = json.loads(row['categories']) if row['categories'] else []
                    subscribers[row['user_id']] = categories
                return subscribers
        except Exception as e:
            logger.error(f"Ошибка при получении списка подписчиков: {e}")
            return {}

    # TODO: Переписать остальные методы (get_unprocessed_messages, mark_message_as_processed, add_subscriber, get_subscribers_for_category) на asyncpg 

    async def update_user_niches(self, user_id, niches):
        """Обновляет ниши пользователя (полная замена)"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id FROM subscribers WHERE user_id = $1", user_id
            )
            if row:
                await conn.execute(
                    "UPDATE subscribers SET categories = $1 WHERE user_id = $2",
                    json.dumps(niches),
                    user_id,
                )
                logger.info(f"💾 Обновлены ниши пользователя {user_id}: {niches}")
            else:
                await conn.execute(
                    """
                    INSERT INTO subscribers (user_id, categories, trial_until)
                    VALUES ($1, $2, NULL)
                    """,
                    user_id,
                    json.dumps(niches),
                )
                logger.info(f"👤 Создан новый пользователь {user_id} с нишами: {niches}")
        if niches:
            await self.start_trial_if_needed(user_id)

    # ==================== МЕТОДЫ ДЛЯ РАБОТЫ СО СТРАНАМИ ====================
    
    async def get_user_countries(self, user_id):
        """Получает список выбранных стран пользователя"""
        async with self.pool.acquire() as conn:
            # Создаем колонку countries, если её нет
            try:
                await conn.execute(
                    """
                    ALTER TABLE subscribers 
                    ADD COLUMN IF NOT EXISTS countries JSONB DEFAULT '[]'::jsonb
                    """
                )
            except Exception:
                pass  # Колонка уже существует
            
            row = await conn.fetchrow(
                'SELECT countries FROM subscribers WHERE user_id = $1',
                user_id
            )
            if row and row['countries']:
                countries = row['countries']
                logger.info(f"🔍 get_user_countries для {user_id}: тип={type(countries)}, значение={countries}, repr={repr(countries)}")
                
                # Если это строка (JSON), парсим её
                if isinstance(countries, str):
                    try:
                        parsed = json.loads(countries)
                        result = parsed if isinstance(parsed, list) else []
                        logger.info(f"🔍 Парсинг строки: {result}")
                        return result
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка парсинга JSON строки для {user_id}: {e}")
                        return []
                
                # Если это уже список Python, возвращаем как есть
                if isinstance(countries, list):
                    logger.info(f"🔍 Возвращаем список как есть: {countries}")
                    return countries
                
                # JSONB в asyncpg может быть специальным объектом (например, asyncpg.types.pgjsonb.Json)
                # Пробуем преобразовать через json.loads, если это возможно
                try:
                    # Если это объект с методом __str__ или можно преобразовать в строку
                    if hasattr(countries, '__str__'):
                        str_repr = str(countries)
                        # Пробуем распарсить как JSON
                        try:
                            parsed = json.loads(str_repr)
                            if isinstance(parsed, list):
                                logger.info(f"🔍 Преобразование через str() и json.loads: {parsed}")
                                return parsed
                        except:
                            pass
                except:
                    pass
                
                # Если это итерируемый объект (но не строка), пробуем преобразовать в список
                if hasattr(countries, '__iter__') and not isinstance(countries, (str, bytes)):
                    try:
                        if isinstance(countries, dict):
                            logger.warning(f"⚠️ countries для {user_id} это dict, возвращаем []")
                            return []
                        # Пробуем преобразовать в список
                        result = list(countries) if countries else []
                        logger.info(f"🔍 Преобразование итерируемого объекта в список: {result}")
                        return result
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка преобразования countries для {user_id}: {e}")
                        return []
                
                logger.warning(f"⚠️ Неизвестный тип countries для {user_id}: {type(countries)}, значение: {countries}")
                return []
            return []
    
    async def update_user_countries(self, user_id, countries):
        """Обновляет список выбранных стран пользователя"""
        async with self.pool.acquire() as conn:
            # Создаем колонку countries, если её нет
            try:
                await conn.execute(
                    """
                    ALTER TABLE subscribers 
                    ADD COLUMN IF NOT EXISTS countries JSONB DEFAULT '[]'::jsonb
                    """
                )
            except Exception:
                pass  # Колонка уже существует
            
            # Проверяем, существует ли пользователь
            row = await conn.fetchrow('SELECT user_id FROM subscribers WHERE user_id = $1', user_id)
            if row:
                # Обновляем существующего пользователя
                await conn.execute(
                    'UPDATE subscribers SET countries = $1 WHERE user_id = $2',
                    json.dumps(countries), user_id
                )
                logger.info(f"💾 Обновлены страны пользователя {user_id}: {countries}")
            else:
                # Создаем нового пользователя
                await conn.execute(
                    'INSERT INTO subscribers (user_id, countries) VALUES ($1, $2)',
                    user_id, json.dumps(countries)
                )
                logger.info(f"👤 Создан новый пользователь {user_id} со странами: {countries}")

    # ==================== МЕТОДЫ ДЛЯ РЕФЕРАЛЬНОЙ СИСТЕМЫ ====================
    
    async def get_user_balance(self, user_id):
        """Получает баланс и реферальную информацию пользователя"""
        async with self.pool.acquire() as conn:
            # Создаем колонки для реферальной системы, если их нет
            try:
                await conn.execute(
                    """
                    ALTER TABLE subscribers 
                    ADD COLUMN IF NOT EXISTS referral_code TEXT,
                    ADD COLUMN IF NOT EXISTS referred_by BIGINT,
                    ADD COLUMN IF NOT EXISTS balance INTEGER DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS total_referrals INTEGER DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS total_earned INTEGER DEFAULT 0
                    """
                )
            except Exception:
                pass  # Колонки уже существуют
            
            row = await conn.fetchrow(
                'SELECT referral_code, balance, total_referrals FROM subscribers WHERE user_id = $1',
                user_id
            )
            
            if row:
                referral_code = row['referral_code']
                # Если реферального кода нет, генерируем его
                if not referral_code:
                    import secrets
                    referral_code = f"REF{user_id}{secrets.token_hex(4).upper()}"
                    await conn.execute(
                        'UPDATE subscribers SET referral_code = $1 WHERE user_id = $2',
                        referral_code, user_id
                    )
                
                return {
                    'referral_code': referral_code,
                    'balance': row['balance'] or 0,
                    'total_referrals': row['total_referrals'] or 0,
                    'total_earned': 0
                }
            else:
                # Создаем нового пользователя с реферальным кодом
                import secrets
                referral_code = f"REF{user_id}{secrets.token_hex(4).upper()}"
                await conn.execute(
                    'INSERT INTO subscribers (user_id, referral_code, balance, total_referrals) VALUES ($1, $2, $3, $4)',
                    user_id, referral_code, 0, 0
                )
                return {
                    'referral_code': referral_code,
                    'balance': 0,
                    'total_referrals': 0,
                    'total_earned': 0
                }
    
    async def is_user_on_trial(self, user_id):
        """Активный триал: trial_until в будущем и нет платной подписки."""
        st = await self.get_subscription_status(user_id)
        return st["trial_active"]