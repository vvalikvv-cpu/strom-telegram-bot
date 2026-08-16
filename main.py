import datetime
import os
import requests

# ⚙️ Считываем секреты GitHub
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

ZONES = {
    "NO1": "Øst-Norge (Oslo)",
    "NO2": "Sør-Norge (Kristiansand)",
    "NO3": "Midt-Norge (Trondheim)",
    "NO4": "Nord-Norge (Tromsø)",
    "NO5": "Vest-Norge (Bergen)",
}


def fetch_prices(target_date: datetime.date):
  """Сбор цен по всем 5 зонам."""
  year = target_date.strftime("%Y")
  month_day = target_date.strftime("%m-%d")
  zones_summary = {}

  for zone_code, zone_name in ZONES.items():
    url = f"https://www.hvakosterstrommen.no/api/v1/prices/{year}/{month_day}_{zone_code}.json"
    response = requests.get(url, timeout=15)
    if response.status_code != 200:
      continue

    data = response.json()
    parsed = []
    for item in data:
      start_hour = item["time_start"][11:16]
      end_hour = item["time_end"][11:16]
      price_ore = round(item["NOK_per_kWh"] * 100, 1)
      parsed.append(
          {"period": f"{start_hour}-{end_hour}", "price_ore": price_ore}
      )

    prices = [p["price_ore"] for p in parsed]
    avg_price = round(sum(prices) / len(prices), 1)
    min_hour = min(parsed, key=lambda x: x["price_ore"])
    max_hour = max(parsed, key=lambda x: x["price_ore"])

    zones_summary[zone_name] = {
        "snitt": avg_price,
        "billigst": f"{min_hour['period']} ({min_hour['price_ore']} øre)",
        "dyrest": f"{max_hour['period']} ({max_hour['price_ore']} øre)",
    }

  return zones_summary


def get_data():
  """Берем цены на завтра, а если их еще нет — на сегодня."""
  tomorrow = datetime.date.today() + datetime.timedelta(days=1)
  zones_data = fetch_prices(tomorrow)
  active_date = tomorrow

  if not zones_data:
    today = datetime.date.today()
    zones_data = fetch_prices(today)
    active_date = today

  return {"date_str": active_date.strftime("%d.%m.%Y"), "zones": zones_data}


def get_working_gemini_model() -> str:
  """Автоматический поиск активной модели Gemini."""
  try:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    res = requests.get(url, timeout=10)
    if res.status_code == 200:
      models_list = res.json().get("models", [])
      # Ищем Flash модель с поддержкой генерации текста
      for m in models_list:
        name = m.get("name", "")
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" in methods and "flash" in name.lower():
          return name
      # Если Flash нет, берем любую подходящую
      for m in models_list:
        name = m.get("name", "")
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" in methods:
          return name
  except Exception:
    pass
  return "models/gemini-1.5-flash"


def fallback_post_generator(stats: dict) -> str:
  """Резервный шаблон поста на чистом норвежском языке."""
  text = f"⚡ *Dagens og morgendagens spotpriser ({stats['date_str']})*\n\n"
  text += "Her er en rask oversikt over strømprisene i Norge (spotpris i øre/kWh, eks. mva/nettleie):\n\n"

  for zone_name, info in stats["zones"].items():
    text += f"📍 *{zone_name}*\n"
    text += f"• Snitt: *{info['snitt']} øre*\n"
    text += f"• 🟢 Billigst: {info['billigst']}\n"
    text += f"• 🔴 Dyrest: {info['dyrest']}\n\n"

  text += "💡 *Smarte sparetips:*\n"
  text += (
      "🚗 Lad elbilen og sett på klesvasken i de grønne (billigste) timene.\n"
  )
  text += "❌ Unngå unødvendig strømbruk under pristoppene.\n\n"
  text += "_Følg med daglig for oppdaterte strømvarsler!_"
  return text


def generate_post(stats: dict) -> str:
  """Генерация через Gemini с автоматическим резервом."""
  model_name = get_working_gemini_model()
  prompt = f"""
Du er en hyggelig og presis norsk strøm-assistent for en Telegram-kanal.
Lag et ryddig og engasjerende dagsinnlegg om spotpriser på strøm for HELE Norge for dato {stats['date_str']}.

📊 DATA PER PRISOMRÅDE (spotpris i øre/kWh, eks. mva og nettleie):
{stats['zones']}

📌 KRAV TIL INNLEGGET:
1. Skriv på feilfritt og naturlig norsk (bokmål) med relevante emojier (⚡, 🇳🇴, 🟢, 🔴, 💡, 🚗).
2. Struktur:
   - Overskrift: ⚡ Strømpriser for hele Norge ({stats['date_str']})
   - Kort oversikt per område (NO1–NO5): snittpris, billigste time og dyreste time.
   - 2-3 konkrete sparetips (anbefalt tid for elbillading og klesvask).
3. Bruk Telegram Markdown (*fet tekst*, _kursiv_).
4. Hold innlegget under 180 ord.
"""

  url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GEMINI_API_KEY}"
  payload = {
      "contents": [{"parts": [{"text": prompt}]}],
      "generationConfig": {"temperature": 0.3},
  }

  try:
    response = requests.post(url, json=payload, timeout=20)
    if response.status_code == 200:
      data = response.json()
      return data["candidates"][0]["content"]["parts"][0]["text"]
  except Exception as e:
    print(f"⚠️ Переходим на резервный генератор: {e}")

  return fallback_post_generator(stats)


def send_telegram(text: str):
  """Отправка сообщения в Telegram-канал."""
  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
  payload = {
      "chat_id": TELEGRAM_CHAT_ID,
      "text": text,
      "parse_mode": "Markdown",
      "disable_web_page_preview": True,
  }
  response = requests.post(url, json=payload, timeout=15)
  response.raise_for_status()


if __name__ == "__main__":
  data = get_data()
  if not data["zones"]:
    print("❌ Не удалось получить данные с сервера цен.")
  else:
    print("🤖 Формируем пост...")
    post = generate_post(data)
    print("🚀 Отправляем в Telegram...")
    send_telegram(post)
    print("✅ Пост опубликован!")
