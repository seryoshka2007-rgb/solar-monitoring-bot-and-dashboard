import asyncio
import logging
import app
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

async def main():
    token = app.BOT_TOKEN
    print("BOT_TOKEN задан:", bool(token), "| длина:", len(token or ""))
    print("ALLOWED_CHAT_IDS:", app.ALLOWED_CHAT_IDS)

    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        me = await bot.get_me()
        print(f"Telegram API: OK, бот @{me.username}")
    except Exception as e:
        print("get_me ERROR:", type(e).__name__, e)
        await bot.session.close()
        return

    for chat_id in app.ALLOWED_CHAT_IDS:
        try:
            await bot.send_message(chat_id, "✅ Тест отправки из solar-bot")
            print(f"send_message -> {chat_id}: OK")
        except Exception as e:
            print(f"send_message -> {chat_id}: {type(e).__name__}: {e}")

    try:
        text = await app.make_completed_report("yesterday")
        print("Отчёт сформирован, тип:", type(text).__name__)
    except Exception as e:
        print("make_completed_report ERROR:", type(e).__name__, e)

    await bot.session.close()

asyncio.run(main())
