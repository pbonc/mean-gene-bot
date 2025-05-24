import os
import json
import re
from datetime import datetime

# Set bot_dir to the parent directory ("bot") of tests
bot_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUOTES_JSON = os.path.join(bot_dir, "data", "quotes.json")
OUTPUT_JSON = os.path.join(bot_dir, "data", "quotes.cleaned.json")

missing_1802 = {
    "text": "This is the missing quote at key 1802.",
    "user": "@example_user",
    "context": "Example Context",
    "date": "05/23/2025"
}

def normalize_date(date_str):
    if not date_str or not isinstance(date_str, str):
        return ""
    date_formats = [
        "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%m-%d-%y",
        "%d/%m/%Y", "%d/%m/%y"
    ]
    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%m/%d/%Y")
        except Exception:
            continue
    return date_str

def clean_text(text):
    if text is None:
        return ""
    return re.sub(r'"\s*$', '', text.strip())

def main():
    with open(QUOTES_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    for key, value in data.items():
        if "text" in value:
            value["text"] = clean_text(value["text"])
        if "date" in value:
            value["date"] = normalize_date(value["date"])

    data["1802"] = missing_1802

    for i in range(1803, 1811):
        if str(i) not in data:
            data[str(i)] = {
                "text": "",
                "user": "",
                "context": "",
                "date": ""
            }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Cleaned file written to {OUTPUT_JSON}")

if __name__ == "__main__":
    main()