import os
import asyncio
from datetime import datetime
import aiohttp
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import google.generativeai as genai

# Токены и секреты из GitHub Secrets
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Ссылка на твой WebApp калькулятор
WEBAPP_URL = "https://vvalikvv-cpu.github.io/strom-telegram-bot/"

async def fetch_prices():
    now = datetime.now()
    y = now.strftime("%Y")
    m_d = now.strftime("%m-%d")
    
    # Собираем данные по Осло (NO1) для примера
    url = f"https://www.hvakosterstrommen.no/api/v1/prices/{y}/{m_d}_NO1.json"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            return None

def format_prompt(prices):
    # Находим минимальную, максимальную и среднюю цену
    nok_prices = [p["NOK_per_kWh"] * 1.25 for p in prices] # С учетом 25% MVA
    min_p = min(nok_prices) * 100
    max_p = max(nok_prices) * 100
    avg_p = (sum(nok_prices) / len(nok_prices)) * 100

    prompt = f"""
Lag en kort, engasjerende og profesjonell daglig strømrapport på norsk for Telegram-kanalen 'Strømvarsel Norge'.

Data for NO1 (Oslo / Øst-Norge) i dag:
- Laveste pris: {min_p:.1f} øre/kWh (inkl. MVA)
- Høyeste pris: {max_p:.1f} øre/kWh (inkl. MVA)
- Snittpris: {avg_p:.1f} øre/kWh

Inkluder:
1. En kort oppsummering av dagens prisbilde med emojier (🟢 / 🔴).
2. Praktiske råd for når det lønner seg å lade elbil eller vaske klær.
3. En oppfordring til å sjekke strømkalkulatoren via knappen under.
Hold teksten oversiktlig, moderne og lettlest.
"""
    return prompt

async def main():
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID or not GEMINI_API_KEY:
        print("Mangler nødvendige miljøvariabler!")
        return

    # Настройка Gemini
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")

    prices = await fetch_prices()
    if not prices:
        print("Kunne ikke hente strømpriser.")
        return

    prompt = format_prompt(prices)
    response = model.generate_content(prompt)
    post_text = response.text

    # Создаем кнопку WebApp
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="⚡ Åpne Strømkalkulator",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ]
    ])

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Публикуем сообщение с инлайн-кнопкой в канал
    await bot.send_message(
        chat_id=CHANNEL_ID,
        text=post_text,
        reply_markup=keyboard
    )
    
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
