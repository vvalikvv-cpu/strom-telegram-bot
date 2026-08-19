import os
import asyncio
from datetime import datetime, timedelta
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
WEBAPP_URL = "https://t.me/strom_daily_helper_bot/calc"

async def fetch_prices():
    now = datetime.now()
    # Если запуск после 13:00 по Осло, ориентируемся на цены завтрашнего дня
    target_date = now + timedelta(days=1) if now.hour >= 13 else now
    
    y = target_date.strftime("%Y")
    m_d = target_date.strftime("%m-%d")
    
    url = f"https://www.hvakosterstrommen.no/api/v1/prices/{y}/{m_d}_NO1.json"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return data, target_date
            
            # Резервный запрос цен на сегодня, если на завтра ещё не опубликованы
            fallback_url = f"https://www.hvakosterstrommen.no/api/v1/prices/{now.strftime('%Y')}/{now.strftime('%m-%d')}_NO1.json"
            async with session.get(fallback_url) as fb_response:
                if fb_response.status == 200:
                    return await fb_response.json(), now
            return None, now

def calculate_stats(prices):
    nok_prices = [p["NOK_per_kWh"] * 1.25 for p in prices] # С учетом 25% MVA
    min_p = min(nok_prices) * 100
    max_p = max(nok_prices) * 100
    avg_p = (sum(nok_prices) / len(nok_prices)) * 100
    return min_p, max_p, avg_p, nok_prices

def create_price_chart(nok_prices, is_tomorrow):
    """Генерирует контрастный темный график цен с крупными шрифтами"""
    hours = [f"{i:02d}" for i in range(24)]
    ore_prices = [p * 100 for p in nok_prices]
    
    min_p = min(ore_prices)
    max_p = max(ore_prices)

    colors = []
    for p in ore_prices:
        ratio = (p - min_p) / (max_p - min_p or 1)
        if ratio > 0.65:
            colors.append('#ff3b30') # Пик
        elif ratio > 0.35:
            colors.append('#ffcc00') # Средний
        else:
            colors.append('#34c759') # Дешевый

    fig, ax = plt.subplots(figsize=(11, 5.5), facecolor='#0b1329')
    ax.set_facecolor('#0b1329')

    bars = ax.bar(hours, ore_prices, color=colors, width=0.7, zorder=2)

    ax.grid(axis='y', linestyle='--', alpha=0.18, color='#ffffff', zorder=1)
    ax.tick_params(colors='#94a3b8', labelsize=12)
    for spine in ax.spines.values():
        spine.set_visible(False)

    day_title = "i morgen" if is_tomorrow else "i dag"
    ax.set_title(f"Strømpriser {day_title} (NO1 Oslo / Øst-Norge) — øre/kWh inkl. MVA", 
                 color='#00e5ff', fontsize=16, pad=18, fontweight='bold')
    
    # Крупные метки цен над минимальным и максимальным столбцами
    for bar, val in zip(bars, ore_prices):
        if val == max_p or val == min_p:
            ax.text(bar.get_x() + bar.get_width()/2, val + 2.0, f"{val:.0f}".replace('.', ','), 
                    ha='center', va='bottom', color='#ffffff', fontsize=11, fontweight='bold')

    plt.tight_layout()
    chart_path = "strom_chart.png"
    plt.savefig(chart_path, dpi=220, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    return chart_path

def generate_local_report(min_p, max_p, avg_p, is_tomorrow):
    day_word = "i morgen" if is_tomorrow else "i dag"
    header_word = "Morgendagens" if is_tomorrow else "Dagens"
    
    min_str = f"{min_p:.1f}".replace('.', ',')
    max_str = f"{max_p:.1f}".replace('.', ',')
    avg_str = f"{avg_p:.1f}".replace('.', ',')

    return f"""⚡ **{header_word} strømrapport for NO1 (Øst-Norge)**

Her er prisbildet for {day_word} (inkl. 25% MVA):
🟢 **Laveste pris:** {min_str} øre/kWh
🔴 **Høyeste pris:** {max_str} øre/kWh
📊 **Snittpris:** {avg_str} øre/kWh

💡 **Smarte sparetips:**
• Planlegg elbillading og klesvask i de grønne timene på grafen.
• Unngå unødvendig strømbruk i de røde topptimene.

Beregn nøyaktig kostnad for dine apparater i kalkulatoren under! 👇"""

def generate_text(min_p, max_p, avg_p, is_tomorrow):
    day_word = "i morgen" if is_tomorrow else "i dag"
    header_word = "Morgendagens" if is_tomorrow else "Dagens"

    prompt = f"""
Lag en kort, engasjerende strømrapport på norsk for Telegram-kanalen 'Strømvarsel Norge'.

Data for NO1 (Oslo / Øst-Norge) for {day_word}:
- Laveste pris: {min_p:.1f} øre/kWh (inkl. MVA)
- Høyeste pris: {max_p:.1f} øre/kWh (inkl. MVA)
- Snittpris: {avg_p:.1f} øre/kWh

Inkluder:
1. Overskrift som tydelig nevner '{header_word} strømpriser ({day_word})'.
2. Oppsummering av prisnivået med emojier (🟢 / 🔴).
3. Råd om å bruke strøm i grønne timer og unngå røde topper på grafen.
4. Oppfordring til å åpne kalkulatoren via knappen under.
Bruk komma som desimalskilletegn (f.eks. 174,2). Hold teksten under 110 ord, ryddig og moderne.
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

    return generate_local_report(min_p, max_p, avg_p, is_tomorrow)

async def main():
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        print("Mangler nødvendige miljøvariabler!")
        return

    prices, target_date = await fetch_prices()
    if not prices:
        print("Kunne ikke hente strømpriser.")
        return

    is_tomorrow = (target_date.date() > datetime.now().date())
    min_p, max_p, avg_p, nok_prices = calculate_stats(prices)
    post_text = generate_text(min_p, max_p, avg_p, is_tomorrow)
    chart_path = create_price_chart(nok_prices, is_tomorrow)

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
            photo=BufferedInputFile(photo_file.read(), filename="stromrapport.png"),
            caption=post_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
