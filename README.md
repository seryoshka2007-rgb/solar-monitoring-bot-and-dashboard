# Solar Bot — SAKO SUNON V

Стартовый проект для мониторинга SAKO SUNON V.

Сейчас:
- Telegram bot
- InfluxDB
- тестовый MockProvider
- /status
- архитектура для /day /week /month /year
- тестовый опрос каждые 10 секунд

Позже источник данных заменяется отдельно:
- SAKO USB
- SAKO RS232
- SmartESS/EyeBond local

Главный принцип:
Telegram, база и аналитика не знают, откуда пришли данные.
Любой источник преобразует данные инвертора в единый Telemetry.

Запуск:
1. cp config/.env.example config/.env
2. заполнить TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID
3. docker compose up -d --build
4. docker compose logs -f solar-bot
