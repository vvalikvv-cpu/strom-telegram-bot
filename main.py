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
    
    url = f"https://www.hvakosterstrommen.no/api/v1/prices/{y}/{m_d}_NO1.json"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            return None

def calculate_stats(prices):
    nok_prices = [p["NOK_per_kWh"] * 1.25 for p in prices] # С учетом 25% MVA
    min_p = min(nok_prices) * 100
    max_p = max(nok_prices) * 100
    avg_p = (sum(nok_prices) / len(nok_prices)) * 100
    return min_p, max_p, avg_p

def generate_local_report(min_p, max_p, avg_p):
    """Надежный локальный отчет на случай сбоя API"""
    return f"""⚡ **Dagens strømrapport for NO1 (Øst-Norge)**

Her er dagens prisbilde (inkl. 25% MVA):
🟢 **Laveste pris:** {min_p:.1f} øre/kWh
🔴 **Høyeste pris:** {max_p:.1f} øre/kWh
📊 **Snittpris:** {avg_p:.1f} øre/kWh

💡 **Smarte sparetips:**
• Lad elbilen og sett på klesvask i de billigste timene for å spare penger.
• Unngå unødvendig strømforbruk i ettermiddagsrushet.

Beregn nøyaktig hva det koster å bruke dine apparater i dag via kalkulatoren under! 👇"""

def generate_text(min_p, max_p, avg_p):
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
    if GEMINI_API_KEY:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            # Используем актуальные модели
            for model_name in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
                try:
                    model = genai.GenerativeModel(model_name)
                    res = model.generate_content(prompt)
                    if res and res.text:
                        return res.text
                except Exception as model_err:
                    print(f"Modell {model_name} feilet: {model_err}")
        except Exception as e:
            print(f"Gemini API feilet: {e}")

    # Если Gemini не ответил, возвращаем резервный шаблон
    return generate_local_report(min_p, max_p, avg_p)

async def main():
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        print("Mangler nødvendige miljøvariabler (TELEGRAM_BOT_TOKEN / CHANNEL_ID)!")
        return

    prices = await fetch_prices()
    if not prices:
        print("Kunne ikke hente strømpriser.")
        return

    min_p, max_p, avg_p = calculate_stats(prices)
    post_text = generate_text(min_p, max_p, avg_p)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="⚡ Åpne Strømkalkulator",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ]
    ])

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    await bot.send_message(
        chat_id=CHANNEL_ID,
        text=post_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
