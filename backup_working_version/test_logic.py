from ai_sniper import SemanticSniper
import logging

# Настройка простого логгирования в консоль
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def test_system():
    # Инициализация
    print("⏳ Загрузка модели...")
    sniper = SemanticSniper(threshold=0.50)  # Можно поиграть с порогом
    print("✅ Модель загружена.\n")

    # Тестовые фразы: (Текст, Ожидаемый результат)
    test_cases = [
        # --- БЛОК 1: ЧИСТЫЙ СПРОС ---
        ("Сниму виллу в Убуде на 2 месяца, бюджет 3000$", "Недвижимость (Спрос)"),
        ("Ищу комнату в гесте, заезжаю завтра", "Недвижимость (Спрос)"),
        ("Ребята, кто сдает байки? Нужен nmax", "Аренда байков"),  # Проверка другой ниши
        
        # --- БЛОК 2: ЧИСТОЕ ПРЕДЛОЖЕНИЕ ---
        ("Сдается шикарная вилла, 3 спальни, бассейн. Пишите в лс.", "Недвижимость (Предложение)"),
        ("Available for rent. 2 bedroom villa in Canggu.", "Недвижимость (Предложение)"),
        ("Освободилась комната в нашей вилле, ищем соседа.", "Недвижимость (Предложение)"),
        
        # --- БЛОК 3: ХИТРЫЕ / СМЕШАННЫЕ / МУСОР ---
        ("Сдаю квартиру в Москве, пишите", "Недвижимость (Предложение)"),  # Гео вы не фильтруете тут, только интент
        ("Посоветуйте фотографа для съемки виллы", "Фотограф"),  # Тут есть слово "вилла", но вектор "Фотографа" должен победить
        ("Я риелтор, помогу снять жилье, комиссия 50%", "Недвижимость (Спрос)?"),  # Спорный момент: это риелтор, ищущий клиента
    ]

    print(f"{'ТЕКСТ СООБЩЕНИЯ':<60} | {'ВЕРДИКТ СИСТЕМЫ':<30} | {'РЕЗУЛЬТАТ'}")
    print("-" * 110)

    for text, expected in test_cases:
        # Эмуляция работы monitor.py
        result = sniper.analyze(text)
        
        niche = result['niche'] if result['is_lead'] else "❌ (Отсеяно)"
        score = result['score']
        reason = result['reason']
        
        # Визуализация совпадения
        if niche == expected or (expected.endswith("?") and niche.startswith(expected[:-1])):
            status = "✅ OK"
        else:
            status = f"⚠️ MISMATCH (ожидалось: {expected})"
        if not result['is_lead'] and "❌" in expected:
            status = "✅ OK"

        print(f"{text[:58]:<60} | {str(niche):<20} ({score}%) | {status}")
        if result['reason'] != 'match' and result['reason'] != 'supply_match':
            print(f"{' '*60} | Reason: {reason}")

if __name__ == "__main__":
    test_system()
