import asyncpg
import json
import logging
from typing import List

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, dsn):
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(dsn=self.dsn)

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

    async def add_subscriber(self, user_id, categories):
        """Добавляет нового подписчика или обновляет существующего"""
        async with self.pool.acquire() as conn:
            from datetime import datetime, timedelta, timezone
            from config import TRIAL_DAYS
            
            try:
                # Проверяем, существует ли пользователь
                existing_user = await conn.fetchrow(
                    'SELECT user_id, trial_until FROM subscribers WHERE user_id = $1',
                    user_id
                )
                
                if existing_user:
                    # Пользователь существует - обновляем только категории, не трогаем триал
                    await conn.execute(
                        '''
                        UPDATE subscribers SET categories = $2, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = $1
                        ''',
                        user_id, json.dumps(categories)
                    )
                    logger.info(f"✅ Обновлены категории для существующего пользователя {user_id}")
                else:
                    # Новый пользователь - создаем с триалом
                    trial_until = datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)
                    await conn.execute(
                        '''
                        INSERT INTO subscribers (user_id, categories, countries, settings, trial_until)
                        VALUES ($1, $2, $3, $4, $5)
                        ''',
                        user_id, json.dumps(categories), json.dumps([]), json.dumps({}), trial_until
                    )
                    logger.info(f"✅ Новый пользователь {user_id} создан с триалом на {TRIAL_DAYS} дней (до {trial_until})")
            except Exception as e:
                logger.error(f"❌ Ошибка при создании/обновлении пользователя {user_id}: {e}")
                # Пробуем создать без дополнительных полей (для обратной совместимости)
                try:
                    # Проверяем, существует ли пользователь
                    existing_user = await conn.fetchrow(
                        'SELECT user_id FROM subscribers WHERE user_id = $1',
                        user_id
                    )
                    
                    if existing_user:
                        await conn.execute(
                            '''
                            UPDATE subscribers SET categories = $2 WHERE user_id = $1
                            ''',
                            user_id, json.dumps(categories)
                        )
                    else:
                        # Новый пользователь - создаем с триалом
                        trial_until = datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)
                        await conn.execute(
                            '''
                            INSERT INTO subscribers (user_id, categories, trial_until)
                            VALUES ($1, $2, $3)
                            ''',
                            user_id, json.dumps(categories), trial_until
                        )
                        logger.info(f"✅ Пользователь {user_id} создан в упрощенном режиме с триалом на {TRIAL_DAYS} дней")
                except Exception as e2:
                    logger.error(f"❌ Критическая ошибка при создании пользователя {user_id}: {e2}")
                    raise

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
                rows = await conn.fetch('SELECT user_id, categories, countries, subscription_active, subscription_until, trial_until FROM subscribers')
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
                    "сша": "usa",
                    "индия": "goa",
                    "юар": "cape_town",
                    "россия": "russia",
                    "армения": "armenia",
                    "сербия": "serbia",
                    "черногория": "montenegro",
                    "испания": "spain",
                    "уругвай": "uruguay",
                    "украина": "ukraine",
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
            # Проверяем, существует ли пользователь
            row = await conn.fetchrow('SELECT user_id FROM subscribers WHERE user_id = $1', user_id)
            if row:
                # Обновляем существующего пользователя
                await conn.execute(
                    'UPDATE subscribers SET categories = $1 WHERE user_id = $2',
                    json.dumps(niches), user_id
                )
                logger.info(f"💾 Обновлены ниши пользователя {user_id}: {niches}")
            else:
                # Создаем нового пользователя
                await conn.execute(
                    'INSERT INTO subscribers (user_id, categories) VALUES ($1, $2)',
                    user_id, json.dumps(niches)
                )
                logger.info(f"👤 Создан новый пользователь {user_id} с нишами: {niches}")

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
        """
        Проверяет, находится ли пользователь на триале (не имеет активной подписки)
        Возвращает True если пользователь на триале, False если имеет подписку
        """
        async with self.pool.acquire() as conn:
            # Создаем колонки для подписки, если их нет
            try:
                await conn.execute(
                    """
                    ALTER TABLE subscribers 
                    ADD COLUMN IF NOT EXISTS subscription BOOLEAN DEFAULT FALSE,
                    ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP
                    """
                )
            except Exception:
                pass  # Колонки уже существуют
            
            row = await conn.fetchrow(
                'SELECT subscription, trial_ends_at FROM subscribers WHERE user_id = $1',
                user_id
            )
            
            if not row:
                # Если пользователя нет в базе, считаем его триальным
                return True
            
            # Если есть активная подписка - не триал
            if row.get('subscription', False):
                return False
            
            # Если есть trial_ends_at, проверяем, не истек ли триал
            trial_ends_at = row.get('trial_ends_at')
            if trial_ends_at:
                from datetime import datetime
                if isinstance(trial_ends_at, str):
                    trial_ends_at = datetime.fromisoformat(trial_ends_at.replace('Z', '+00:00'))
                # Если триал истек, считаем что пользователь не на триале (нужна подписка)
                if datetime.now() > trial_ends_at:
                    return False
            
            # По умолчанию считаем триальным
            return True