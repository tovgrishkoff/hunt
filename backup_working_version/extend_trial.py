import asyncio
import logging
from database import Database
from telethon import TelegramClient
from config import API_ID, API_HASH, PHONE_NUMBER

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('extend_trial.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def extend_trial_period():
    """Продление пробного периода для всех пользователей"""
    try:
        # Инициализация базы данных
        db = Database()
        await db.initialize()
        
        # Продление пробного периода
        await db.extend_trial_period(hours=48)
        
        # Получение списка пользователей с истекшим триалом
        expired_users = await db.get_expired_trial_users()
        
        # Инициализация клиента Telegram
        client = TelegramClient('extend_trial_session', API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            while True:
                try:
                    # Запрашиваем код подтверждения
                    await client.send_code_request(PHONE_NUMBER)
                    logger.info("Код подтверждения отправлен на ваш телефон")
                    code = input('Введите код подтверждения: ')
                    
                    try:
                        # Пытаемся войти с кодом
                        await client.sign_in(PHONE_NUMBER, code)
                        logger.info("Успешная авторизация!")
                        break
                    except Exception as e:
                        if "password" in str(e).lower():
                            # Если требуется пароль двухфакторной аутентификации
                            logger.info("Требуется пароль двухфакторной аутентификации")
                            password = 'xT9$mK2pL7@fR3nQ'  # Пароль двухфакторной аутентификации
                            try:
                                # Пытаемся войти с паролем
                                await client.sign_in(password=password)
                                logger.info("Успешная авторизация с паролем!")
                                break
                            except Exception as e:
                                logger.error(f"Ошибка входа с паролем: {e}")
                                return
                        else:
                            logger.error(f"Неверный код подтверждения. Попробуйте еще раз.")
                            continue
                except Exception as e:
                    logger.error(f"Ошибка при запросе кода: {e}")
                    return
        
        # Отправка уведомлений пользователям
        for user in expired_users:
            try:
                message = (
                    "🎉 Хорошие новости! Мы продлили ваш пробный период на 48 часов.\n\n"
                    "Теперь у вас есть больше времени, чтобы оценить все преимущества нашего сервиса.\n\n"
                    "Если у вас есть вопросы или нужна помощь, обращайтесь!"
                )
                await client.send_message(user['user_id'], message)
                logger.info(f"Уведомление отправлено пользователю {user['user_id']}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления пользователю {user['user_id']}: {e}")
        
        await client.disconnect()
        await db.close()
        
        logger.info("Продление пробного периода успешно завершено")
        
    except Exception as e:
        logger.error(f"Ошибка при продлении пробного периода: {e}")

if __name__ == "__main__":
    asyncio.run(extend_trial_period()) 