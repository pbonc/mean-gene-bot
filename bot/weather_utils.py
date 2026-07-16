import os
import aiohttp
import random

def get_weather_emoji(condition):
    """Map weather condition text to appropriate emoji"""
    condition_lower = condition.lower()
    
    # Clear/Sunny conditions
    if any(word in condition_lower for word in ['sunny', 'clear']):
        return '☀️'
    
    # Cloudy conditions
    elif any(word in condition_lower for word in ['partly cloudy', 'partly sunny']):
        return '⛅'
    elif any(word in condition_lower for word in ['cloudy', 'overcast']):
        return '☁️'
    
    # Rain conditions
    elif any(word in condition_lower for word in ['heavy rain', 'torrential']):
        return '🌧️'
    elif any(word in condition_lower for word in ['light rain', 'drizzle', 'mist']):
        return '🌦️'
    elif any(word in condition_lower for word in ['rain', 'shower']):
        return '🌧️'
    
    # Snow conditions
    elif any(word in condition_lower for word in ['heavy snow', 'blizzard']):
        return '❄️'
    elif any(word in condition_lower for word in ['light snow', 'snow shower']):
        return '🌨️'
    elif any(word in condition_lower for word in ['snow', 'sleet']):
        return '❄️'
    
    # Thunderstorm conditions
    elif any(word in condition_lower for word in ['thunderstorm', 'thunder']):
        return '⛈️'
    
    # Fog conditions
    elif any(word in condition_lower for word in ['fog', 'haze', 'mist']):
        return '🌫️'
    
    # Wind conditions
    elif any(word in condition_lower for word in ['windy', 'breezy']):
        return '💨'
    
    # Ice conditions
    elif any(word in condition_lower for word in ['ice', 'freezing']):
        return '🧊'
    
    # Default for unknown conditions
    else:
        return '🌤️'
WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEATHER_FILE = os.path.join(WORKSPACE_ROOT, "assets", "txt", "weather_messages.txt")

async def fetch_weather(location):
    WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY")
    url = f"http://api.weatherapi.com/v1/current.json?key={WEATHERAPI_KEY}&q={location}&aqi=no"
    import logging
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logging.error(
                        f"[WEATHER ERROR] HTTP {resp.status} for {location}: {body[:400]}", exc_info=False
                    )
                    return f"{location} : [weather error]"
                try:
                    data = await resp.json()
                except aiohttp.ContentTypeError as e:
                    body = await resp.text()
                    logging.error(
                        f"[WEATHER ERROR] JSON decode error for {location}: {e} body={body[:400]}",
                        exc_info=True,
                    )
                    return f"{location} : [weather error]"
                except Exception as e:
                    logging.error(
                        f"[WEATHER ERROR] JSON decode error for {location}: {e}",
                        exc_info=True,
                    )
                    return f"{location} : [weather error]"
                if "current" not in data or "location" not in data:
                    logging.error(f"[WEATHER ERROR] Missing 'current' or 'location' in response for {location}")
                    return f"{location} : [weather error]"
                try:
                    condition = data["current"]["condition"]["text"]
                    temp_f = int(data["current"]["temp_f"])
                    temp_c = int(data["current"]["temp_c"])
                    emoji = get_weather_emoji(condition)
                    return f"{location}: {emoji} {condition}, {temp_f}°F / {temp_c}°C"
                except Exception as e:
                    logging.error(f"[WEATHER ERROR] Exception parsing response for {location}: {e}", exc_info=True)
                    return f"{location} : [weather error]"
    except Exception as e:
        logging.error(f"[WEATHER ERROR] Exception in fetch_weather for {location}: {e}", exc_info=True)
        return f"{location} : [weather error]"

def save_weather_message(msg):
    # Save location to weather_messages.txt if not already present
    location = msg.strip()
    if not location:
        return
    if not os.path.isfile(WEATHER_FILE):
        with open(WEATHER_FILE, "w", encoding="utf-8") as f:
            f.write(location + "\n")
        return
    with open(WEATHER_FILE, "r+", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
        if location not in lines:
            f.write(location + "\n")

def load_weather_messages():
    if not os.path.isfile(WEATHER_FILE):
        return []
    with open(WEATHER_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

import asyncio
async def get_random_weather_messages(n=5):
    locations = load_weather_messages()
    if not locations:
        return ["Weather: N/A"]
    chosen = random.sample(locations, min(n, len(locations)))
    results = []
    for loc in chosen:
        msg = await fetch_weather(loc)
        results.append(msg)
    return results

async def get_any_weather_message():
    locations = load_weather_messages()
    if not locations:
        return "Weather: N/A"
    loc = random.choice(locations)
    return await fetch_weather(loc)
