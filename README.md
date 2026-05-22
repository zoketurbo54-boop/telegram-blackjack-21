# Telegram-бот «21 очко» (Blackjack)

Бот на **aiogram 3** с картинками карт ([deckofcardsapi.com](https://deckofcardsapi.com)), статистикой в SQLite и подпиской **Premium за Telegram Stars** (50 ⭐ / месяц). Без подписки игра недоступна.

## Возможности

- Игра в 21 с inline-кнопками
- Статистика, рекорды, достижения (`/stats`)
- Подписка Stars (`/subscribe`)
- Деплой на VPS (Beget и др.) — см. `deploy/DEPLOY_BEGET.md`

## Быстрый старт (локально)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # вписать BOT_TOKEN
python bot.py
```

## Переменные окружения

См. `.env.example`. Обязательно: `BOT_TOKEN`. Опционально: `TELEGRAM_ADMIN_ID`, `TELEGRAM_PROXY`, настройки таймаутов.

## Лицензия

MIT (при необходимости укажите свою).
