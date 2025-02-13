# bot.py
from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode

BOT_TOKEN = "7631229383:AAHc5p2MxjdC9huvVAOTrW2uG7z-QegWT9Y"

bot = Bot(
    token=BOT_TOKEN,
    default_bot_properties=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
