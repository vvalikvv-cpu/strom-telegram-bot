import os
import asyncio
from datetime import datetime
import aiohttp
import matplotlib.pyplot as plt
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
import google.generativeai as genai

# Токены и секреты из GitHub Secrets
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Прямая ссылка на Mini App
WEBAPP_URL = "https://t.me/strom_daily_helper_bot/calc" # Подставь точный username бота при необходимости

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
    return min_p, max_p, avg_p, nok_prices

def create_price_chart(nok_prices):
    """Генерирует темный стильный график цен на 24 часа"""
    hours = [f"{i:02d}" for i in range(24)]
    ore_prices = [p * 100 for p in nok_prices]
    
    min_p = min(ore_prices)
    max_p = max(ore_prices)

    # Цветовая схема под пики и спады
    colors = []
    for p in ore_prices:
        ratio = (p - min_p) / (max_p - min_p or 1)
        if ratio > 0.65:
            colors.append('#ff3b30') # Красный пик
        elif ratio > 0.35:
            colors.append('#ffcc00') # Желтый
        else:
            colors.append('#34c759') # Зеленый спад

    fig, ax = plt.subplots(figsize=(10, 5), facecolor='#0b1329')
    ax.set_facecolor('#0b1329')

    bars = ax.bar(hours, ore_prices, color=colors, width=0.65, zorder=2)

    # Оформление осей и сетки
    ax.grid(axis='y', linestyle='--', alpha=0.15, color='#ffffff', zorder=1)
    ax.tick_params(colors='#94a3b8', labelsize=10)
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Заголовок и подписи
    ax.set_title("Døgnprofil Strømpris (NO1 Oslo / Øst-Norge) — øre/kWh inkl. MVA", 
                 color='#00e5ff', fontsize=14, pad=15, fontweight='bold')
    
    # Подпись значений над ключевыми столбцами
    for bar, val in zip(bars, ore_prices):
        if val == max_p or val == min_p:
            ax.text(bar.get_x() + bar.get_width()/2, val + 1.5, f"{val:.0f}", 
                    ha='center', va='bottom', color='#ffffff', fontsize=9, fontweight='bold')

    plt.tight_layout()
    chart_path = "strom_chart.png"
    plt.savefig(chart_path, dpi=200, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    return chart_path

def generate_local_report(min_p, max_p, avg_p):
    return f"""⚡ **Dagens strømrapport for NO1 (Øst-Norge)**

Her er dagens prisbilde (inkl. 25% MVA):
🟢 **Laveste pris:** {min_p:.1f} øre/kWh
🔴 **Høyeste pris:** {max_p:.1f} øre/kWh
📊 **Snittpris:** {avg_p:.1f} øre/kWh

💡 **Smarte sparetips:**
• Lad elbilen og kjør klesvask i de grønne timene på grafen.
• Unngå unødvendig forbruk under de røde ettermiddagstoppene.

Beregn nøyaktig pris for dine apparater i kalkulatoren under! 👇"""

def generate_text(min_p, max_p, avg_p):
    prompt = f"""
Lag en kort, engasjerende daglig strømrapport på norsk for Telegram-kanalen 'Strømvarsel Norge'.

Data for NO1 (Oslo / Øst-Norge) i dag:
- Laveste pris: {min_p:.1f} øre/kWh (inkl. MVA)
- Høyeste pris: {max_p:.1f} øre/kWh (inkl. MVA)
- Snittpris: {avg_p:.1f} øre/kWh

Inkluder:
1. En kort oppsummering av dagens prisbilde med emojier (🟢 / 🔴).
2. Tydelig henvisning til grafen for billigste/dyreste timer.
3. Oppfordring til å sjekke strømkalkulatoren via knappen under.
Hold teksten under 120 ord, moderne og lettlest.
"""
    if GEMINI_API_KEY:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
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

    return generate_local_report(min_p, max_p, avg_p)

async def main():
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        print("Mangler nødvendige miljøvariabler!")
        return

    prices = await fetch_prices()
    if not prices:
        print("Kunne ikke hente strømpriser.")
        return

    min_p, max_p, avg_p, nok_prices = calculate_stats(prices)
    post_text = generate_text(min_p, max_p, avg_p)
    chart_path = create_price_chart(nok_prices)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="⚡ Åpne Strømkalkulator",
                url=WEBAPP_URL
            )
        ]
    ])

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    with open(chart_path, "rb") as photo_file:
        await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=BufferedInputFile(photo_file.read(), filename="dognpris.png"),
            caption=post_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
