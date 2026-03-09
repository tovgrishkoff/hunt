# Пресеты рекламных кампаний (спринты)

Три шаблона конфигурации. Чтобы сменить задачу — скопируй нужный файл в `bali.json` и перезапусти контейнеры.

| Файл | Режим |
|------|--------|
| `bali_bot_promo.json` | Реклама бота @Lead_Hunbot (лидген, нативно) |
| `bali_india_retreat.json` | Ретрит в Индию (трансформация, места силы) |
| `bali_real_estate.json` | Продажа виллы на Бали (инвестиции) |

## Команды переключения (выполнять из хоста)

**Включить режим «Реклама бота»:**
```bash
cp /home/tovgrishkoff/PIAR/telegram_promotion_system_bali/config/niches/bali_bot_promo.json /home/tovgrishkoff/PIAR/telegram_promotion_system_bali/config/niches/bali.json && docker restart telegram-bali-marketer telegram-bali-secretary telegram-bali-account-manager
```

**Включить режим «Индия ретрит»:**
```bash
cp /home/tovgrishkoff/PIAR/telegram_promotion_system_bali/config/niches/bali_india_retreat.json /home/tovgrishkoff/PIAR/telegram_promotion_system_bali/config/niches/bali.json && docker restart telegram-bali-marketer telegram-bali-secretary telegram-bali-account-manager
```

**Включить режим «Продажа виллы»:**
```bash
cp /home/tovgrishkoff/PIAR/telegram_promotion_system_bali/config/niches/bali_real_estate.json /home/tovgrishkoff/PIAR/telegram_promotion_system_bali/config/niches/bali.json && docker restart telegram-bali-marketer telegram-bali-secretary telegram-bali-account-manager
```

Текущий рабочий конфиг не трогаем — пресеты только копируются в `bali.json` при смене спринта.
