# 📝 Система релевантных сообщений по тематикам групп

## 🎯 Назначение

Система автоматически определяет тематику группы и выбирает **релевантные сообщения** для постинга.

## 🏷️ Тематики групп

Система определяет 4 тематики:

1. **`real_estate`** - Недвижимость (продажа, инвестиции)
2. **`rental`** - Аренда (виллы, квартиры, байки, авто)
3. **`services`** - Услуги (фотографы, виза, косметология, туры и т.д.)
4. **`general`** - Общие группы (чат, объявления)

## 🔍 Как определяется тематика

Функция `_determine_group_topic()` анализирует `username` и `title` группы и ищет ключевые слова:

### Real Estate ключевые слова:
- property, недвижимость, nedvizhimost, villa, вилла
- estate, sale, продажа, investment, инвестиц
- house, дом, apartment, квартира

### Rental ключевые слова:
- rent, аренда, arenda, rental, прокат
- villa, вилла, house, дом, apartment, квартира
- bike, байк, мотоцикл, motorcycle, авто, car
- vehicle, транспорт

### Services ключевые слова:
- service, услуги, uslugi, помощь, help
- фотограф, photographer, видеограф, videographer
- маникюр, manicure, брови, eyebrows, ресницы, eyelashes
- макияж, makeup, косметолог, cosmetology
- дизайнер, designer, швея, seamstress
- психолог, psychologist, трансфер, transfer
- турагент, tour, ретрит, валюта, currency

### Приоритет определения:
1. Сначала проверяется `real_estate`
2. Затем `rental` (если нет признаков продажи/инвестиций)
3. Затем `services`
4. Иначе `general`

## 📊 Распределение сообщений

Сообщения из `messages.json` группируются по `source_file`:

| Source File | Тематика |
|-------------|----------|
| `messages_sale_property.txt` | real_estate |
| `messages_rental_property.txt` | rental |
| `messages_housing.txt` | rental |
| `messages_bike_rental.txt` | rental |
| `messages_car_rental.txt` | rental |
| `messages_transport.txt` | services |
| `messages_photographer.txt` | services |
| `messages_videographer.txt` | services |
| `messages_manicure.txt` | services |
| `messages_eyebrows.txt` | services |
| `messages_eyelashes.txt` | services |
| `messages_makeup.txt` | services |
| `messages_hair.txt` | services |
| `messages_cosmetology.txt` | services |
| `messages_designer.txt` | services |
| `messages_seamstress.txt` | services |
| `messages_psychological.txt` | services |
| `messages_tourism.txt` | services |
| `messages_family_retreat.txt` | services |
| `messages_currency.txt` | services |
| `messages_hookah.txt` | services |
| `messages_playstation.txt` | services |
| `messages_energy_cleansing.txt` | services |
| `messages_general.txt` | general |
| `messages_morning.txt` | general |
| `messages_noon.txt` | general |
| `messages_evening.txt` | general |

## 🔄 Как работает система

### 1. Инициализация (`initialize()`)

При загрузке сообщения группируются по тематикам:

```python
self.niche_messages = {
    'real_estate': [...],
    'rental': [...],
    'services': [...],
    'general': [...]
}
```

### 2. Постинг (`post_to_group()`)

При отправке поста:

1. Определяется тематика группы: `topic = self._determine_group_topic(group)`
2. Выбираются сообщения из релевантной тематики: `source_messages = self.niche_messages.get(topic, [])`
3. Если нет сообщений для тематики - используется общий список (fallback)
4. Выбирается случайное сообщение: `message_data = random.choice(source_messages)`

### 3. Логирование

В логах видно, какая тематика используется:

```
📋 Using topic 'rental' messages for @Villa_Bali_Arenda_1
📋 No messages for topic 'real_estate', using general pool for @some_group
```

## 📈 Статистика загрузки

При запуске системы логируется статистика:

```
✅ Loaded 15 messages for topic 'real_estate'
✅ Loaded 60 messages for topic 'rental'
✅ Loaded 395 messages for topic 'services'
✅ Loaded 180 messages for topic 'general'
✅ Total 650 messages loaded (grouped by topics)
```

## ✅ Примеры работы

| Группа | Тематика | Примеры сообщений |
|--------|----------|-------------------|
| `@Villa_Bali_Arenda_1` | rental | "Ищу байк в аренду...", "Ищу аренду виллы..." |
| `@balitopoffer` | real_estate | "Ищу недвижимость для инвестиций...", "Продажа виллы..." |
| `@photographer_bali` | services | "Ищу фотографа...", "Нужен видеограф..." |
| `@Bali_Top_Chat` | general | Общие сообщения из general пула |

## 🔧 Настройка

Для добавления новых категорий сообщений:

1. Добавьте mapping в `source_to_topic` словарь
2. Добавьте ключевые слова в `_determine_group_topic()` если нужно изменить определение тематики

---

*Обновлено: 2026-01-11*
