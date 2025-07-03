import json
from bs4 import BeautifulSoup
from datetime import datetime
import time
import os

HTML_FILE = "your_html_file.html"
JSON_FILE = "today_matches.json"
LOG_FILE = "scraper_log.txt"

def log_event(message):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S GMT")
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(f"[{now}] {message}\n")

def parse_match(div):
    def grab_text(selector, count=None):
        elems = div.select(selector)
        return [e.get_text(strip=True) for e in elems][:count] if elems else []

    def grab_single(selector):
        el = div.select_one(selector)
        return el.get_text(strip=True) if el else None

    return {
        "teams": grab_text(".wtmoblnk", 2),
        "team1_form": grab_text(".wtl5contl .last5w, .wtl5contl .last5d, .wtl5contl .last5l"),
        "team2_form": grab_text(".wtl5contr .last5w, .wtl5contr .last5d, .wtl5contr .last5l"),
        "fixture": grab_single(".wtdesklnk"),
        "odds": {
            "1x2": grab_text(".wtmo .wtocell a"),
            "over_under": grab_text(".wtou .wtocell a"),
            "btts": grab_text(".wtbt .wtocell a"),
        },
        "prediction": grab_single(".wtprd"),
        "score": grab_single(".wtsc")
    }

def run_scraper():
    try:
        with open(HTML_FILE, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")

        matches = [parse_match(div) for div in soup.select(".wttr")]

        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(matches, f, indent=2)

        log_event(f"✅ Scrape successful. {len(matches)} matches saved.")
    except Exception as e:
        log_event(f"❌ Scrape failed: {str(e)}")

def scheduler_loop():
    while True:
        now = datetime.utcnow()
        hour = now.hour
        minute = now.minute

        # Run only at 06:00 or 09:00 GMT
        if hour in [6, 9] and minute == 0:
            run_scraper()
            time.sleep(60)  # Wait a minute to avoid duplicate runs
        time.sleep(30)  # Check every 30 seconds

if __name__ == "__main__":
    log_event("🔄 Scraper started.")
    run_scraper()  # Optional: first run now
    scheduler_loop()
