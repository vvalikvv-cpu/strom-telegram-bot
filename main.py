import datetime
import os
import requests

# ⚙️ Считываем ключи из настроек GitHub Secrets
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
  """Запрос цен на определенную дату по всем 5 зонам."""
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
  """Пробуем получить завтрашние цены, если их еще нет — берем сегодняшние."""
  tomorrow = datetime.date.today() + datetime.timedelta(days=1)
  zones_data = fetch_prices(tomorrow)
  active_date = tomorrow

  if not zones_data:
    today = datetime.date.today()
    zones_data = fetch_prices(today)
    active_date = today

  return {"date_str": active_date.strftime("%d.%m.%Y"), "zones": zones_data}


def generate_post(stats: dict) -> str:
  """Создание текста поста через прямой стабильный API Gemini."""
  prompt = f"""
Du er en hyggelig og presis norsk strøm-assistent for en Telegram-kanal.
Lag et ryddig og engasjerende dagsinnlegg om spotpriser på strøm for HELE Norge for dato {stats['date_str']}.

📊 DATA PER PRISOMRÅDE (spotpris i øre/kWh, eks. mva og nettleie):
{stats['zones']}

📌 KRAV TIL INNLEGGET:
1. Skriv på naturlig norsk (bokmål) med relevante emojier (⚡, 🇳🇴, 🟢, 🔴, 💡, 🚗).
2. Struktur:
   - Overskrift: ⚡ Strømpriser for hele Norge ({stats['date_str']})
   - Kort oversikt per område (NO1–NO5): gjennomsnittspris, billigste time og dyreste time.
   - 2-3 konkrete sparetips (anbefalt tid for elbillading og klesvask).
3. Bruk Telegram Markdown (*fet tekst*, _kursiv_).
4. Maks 180 ord.
"""

  models_to_try = ["gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-1.5-pro"]

  for model in models_to_try:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3},
    }
    response = requests.post(url, json=payload, timeout=25)

    if response.status_code == 200:
      result = response.json()
      try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
      except (KeyError, IndexError):
        continue

  raise RuntimeError(
      f"Ошибка ответа Gemini API: {response.status_code} - {response.text}"
  )


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
    print("❌ Не удалось получить данные о ценах.")
  else:
    print("🤖 Нейросеть генерирует пост...")
    post = generate_post(data)
    print("🚀 Отправка в Telegram...")
    send_telegram(post)
    print("✅ Пост успешно опубликован в канале!")
