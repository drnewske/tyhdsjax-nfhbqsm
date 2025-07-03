import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import json
import os

URL = "https://www.windrawwin.com/predictions/today/"
JSON_FILE = "today_matches.json"
LOG_FILE = "scraper_log.txt"

def log(msg):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S GMT")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{now}] {msg}\n")

def parse_match(div):
    def gt(sel): return [e.get_text(strip=True) for e in div.select(sel)]
    def gs(sel): return (div.select_one(sel).get_text(strip=True) if div.select_one(sel) else None)

    return {
        "teams": gt(".wtmoblnk")[:2],
        "team1_form": gt(".wtl5contl .last5w, .wtl5contl .last5d, .wtl5contl .last5l"),
        "team2_form": gt(".wtl5contr .last5w, .wtl5contr .last5d, .wtl5contr .last5l"),
        "fixture": gs(".wtdesklnk"),
        "odds": {
            "1x2": gt(".wtmo .wtocell a"),
            "over_under": gt(".wtou .wtocell a"),
            "btts": gt(".wtbt .wtocell a"),
        },
        "prediction": gs(".wtprd"),
        "score": gs(".wtsc")
    }

def scrape_and_save():
    try:
        resp = requests.get(URL, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        matches = [parse_match(d) for d in soup.select(".wttr")]
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(matches, f, indent=2)

        log(f"✅ Scraped {len(matches)} matches; JSON overwritten.")
    except Exception as e:
        log(f"❌ Scrape failed: {e!s}")

def schedule():
    log("🔄 Scraper started")
    while True:
        now = datetime.utcnow()
        if now.hour in [6, 9] and now.minute == 0:
            scrape_and_save()
            time.sleep(61)  # avoid double trigger
        time.sleep(30)

if __name__ == "__main__":
    scrape_and_save()
    schedule()
