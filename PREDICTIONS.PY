#!/usr/bin/env python3
"""
Enhanced WindrawWin Predictions Scraper using Playwright
FINAL CORRECTED VERSION - This version uses precise, contextual locators
based on the full HTML structure to guarantee correct data extraction.
"""

import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import asyncio
import re

from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError


class EnhancedWindrawWinScraper:
    """Enhanced scraper class for windrawwin.com predictions using Playwright"""

    def __init__(self):
        self.base_url = "https://www.windrawwin.com/predictions/today/"
        self.setup_logging()
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    async def setup_browser(self, playwright):
        """Setup browser with stealth configuration"""
        try:
            self.browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas', '--no-first-run', '--no-zygote',
                    '--single-process', '--disable-gpu', '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
                    '--disable-features=TranslateUI', '--disable-ipc-flooding-protection',
                    '--disable-blink-features=AutomationControlled', '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                java_script_enabled=True,
                locale='en-US',
                timezone_id='America/New_York'
            )
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'permissions', {
                    get: () => ({ query: () => Promise.resolve({ state: 'granted' }) }),
                });
            """)
            self.page = await context.new_page()
            self.logger.info("Browser setup completed successfully")
        except Exception as e:
            self.logger.error(f"Error setting up browser: {e}")
            raise

    async def fetch_page(self) -> bool:
        """Fetch and load the main predictions page with robust checks."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.logger.info(f"Navigating to {self.base_url} (Attempt {attempt + 1}/{max_retries})")
                await self.page.goto(self.base_url, wait_until='domcontentloaded', timeout=60000)
                
                # A more reliable wait for content is to wait for the specific element we need.
                await self.page.wait_for_selector('div.wdwtablest > div.wttr', timeout=30000)
                
                self.logger.info("Page loaded and essential content found.")
                return True
            except PlaywrightTimeoutError:
                self.logger.warning(f"Timeout waiting for content on attempt {attempt + 1}.")
                if attempt == max_retries - 1:
                    self.logger.error("Failed to load page content after multiple retries.")
                    return False
            except Exception as e:
                self.logger.error(f"An error occurred during page fetch on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise
        return False

    def clean_text(self, text: Optional[str]) -> str:
        """Clean and normalize text content, handling None input."""
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text.strip())

    def extract_league_from_fixture(self, fixture_url: Optional[str]) -> str:
        """Dynamically extract league from the fixture URL."""
        if not fixture_url:
            return ""
        try:
            parts = fixture_url.split('/')
            if 'tips' in parts:
                league_part = parts[parts.index('tips') + 1]
                return league_part.replace('-', ' ').title()
        except (ValueError, IndexError):
            self.logger.warning(f"Could not dynamically extract league from URL: {fixture_url}")
        return ""

    async def extract_match_data(self, match_locator) -> Optional[Dict[str, Any]]:
        """
        Extract data from a single match element using precise, contextual, and positional locators.
        THIS IS THE FULLY CORRECTED EXTRACTION LOGIC.
        """
        try:
            # Pre-initialize the data structure
            match_data = {
                "teams": {"home": "", "away": ""}, "fixture": "", "league": "",
                "prediction": {"type": "", "stake": "", "score": ""},
                "odds": {
                    "match_odds": {"home": "", "draw": "", "away": ""},
                    "over_under": {"over": "", "under": ""},
                    "btts": {"yes": "", "no": ""}
                },
                "form": {"home": [], "away": []}, "has_odds": False, "match_url": ""
            }

            # --- Teams, Fixture, and URL ---
            # There are two .wtmoblnk divs for teams, first is home, second is away.
            match_data["teams"]["home"] = self.clean_text(await match_locator.locator('.wtmoblnk').nth(0).text_content())
            match_data["teams"]["away"] = self.clean_text(await match_locator.locator('.wtmoblnk').nth(1).text_content())

            fixture_element = match_locator.locator('.wtdesklnk')
            if await fixture_element.count() > 0:
                match_data["fixture"] = self.clean_text(await fixture_element.text_content())
                fixture_url = await fixture_element.get_attribute('href')
                if fixture_url:
                    # Prepend domain if URL is relative
                    match_data["match_url"] = f"https://www.windrawwin.com{fixture_url}" if fixture_url.startswith('/') else fixture_url
                    match_data["league"] = self.extract_league_from_fixture(fixture_url)

            # --- Prediction Details ---
            # These have unique classes within the row, so direct targeting is safe.
            match_data["prediction"]["stake"] = self.clean_text(await match_locator.locator('.wtstk').text_content())
            match_data["prediction"]["type"] = self.clean_text(await match_locator.locator('.wtprd').text_content())
            match_data["prediction"]["score"] = self.clean_text(await match_locator.locator('.wtsc').text_content())

            # --- *** THE CORRECTED ODDS EXTRACTION *** ---
            # We check if there are links in the odds cells. If so, odds are available.
            match_data["has_odds"] = await match_locator.locator('.wtmo .wtocell a').count() > 0
            if match_data["has_odds"]:
                # Match Odds (1X2): Use positional `nth()` as you suggested.
                odds_1x2 = match_locator.locator('.wtmo .wtocell a')
                match_data["odds"]["match_odds"]["home"] = self.clean_text(await odds_1x2.nth(0).text_content())
                match_data["odds"]["match_odds"]["draw"] = self.clean_text(await odds_1x2.nth(1).text_content())
                match_data["odds"]["match_odds"]["away"] = self.clean_text(await odds_1x2.nth(2).text_content())

                # Over/Under 2.5 Odds: Positional `nth()`
                odds_ou = match_locator.locator('.wtou .wtocell a')
                match_data["odds"]["over_under"]["over"] = self.clean_text(await odds_ou.nth(0).text_content())
                match_data["odds"]["over_under"]["under"] = self.clean_text(await odds_ou.nth(1).text_content())

                # BTTS Odds: Positional `nth()`
                odds_btts = match_locator.locator('.wtbt .wtocell a')
                match_data["odds"]["btts"]["yes"] = self.clean_text(await odds_btts.nth(0).text_content())
                match_data["odds"]["btts"]["no"] = self.clean_text(await odds_btts.nth(1).text_content())

            # --- Team Form (Last 5 Games) ---
            # Helper to parse W/D/L classes
            async def parse_form(form_locator):
                forms = []
                for i in range(await form_locator.count()):
                    item_class = await form_locator.nth(i).get_attribute('class')
                    if 'last5w' in (item_class or ''): forms.append('W')
                    elif 'last5d' in (item_class or ''): forms.append('D')
                    elif 'last5l' in (item_class or ''): forms.append('L')
                return forms

            # Home form is in `.wtl5contl`, Away form is in `.wtl5contr`
            match_data["form"]["home"] = await parse_form(match_locator.locator('.wtl5contl > div'))
            match_data["form"]["away"] = await parse_form(match_locator.locator('.wtl5contr > div'))

            # Final check for essential data before returning
            if match_data["teams"]["home"] and match_data["teams"]["away"]:
                return match_data
            return None

        except Exception as e:
            # Add more context to the error log
            team_name = self.clean_text(await match_locator.locator('.wtmoblnk').first.text_content())
            self.logger.error(f"CRITICAL ERROR processing match row starting with '{team_name}': {e}", exc_info=True)
            return None

    async def scrape_matches(self) -> List[Dict[str, Any]]:
        """Main scraping function to get all today's matches with precise locators."""
        if not await self.fetch_page():
            return []

        matches = []
        try:
            # THIS IS THE KEY FIX: Target only .wttr that are direct children of .wdwtablest
            match_elements = self.page.locator('div.wdwtablest > div.wttr')
            match_count = await match_elements.count()
            self.logger.info(f"Found {match_count} match rows using precise selector.")

            for i in range(match_count):
                match_element = match_elements.nth(i)
                match_data = await self.extract_match_data(match_element)
                if match_data:
                    matches.append(match_data)
                    self.logger.debug(f"Extracted: {match_data['teams']['home']} vs {match_data['teams']['away']}")

            self.logger.info(f"Successfully extracted data for {len(matches)} matches.")
        except Exception as e:
            self.logger.error(f"Error during main scraping loop: {e}", exc_info=True)

        return matches

    def save_data(self, matches: List[Dict[str, Any]]) -> bool:
        """Save matches data to JSON file."""
        current_dir = os.getcwd()
        json_path = os.path.join(current_dir, 'today_matches.json')
        summary_data = {
            "scrape_info": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_matches": len(matches),
                "matches_with_odds": len([m for m in matches if m.get("has_odds")]),
                "source_url": self.base_url
            },
            "matches": matches
        }
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)
            self.logger.info(f"✅ Data saved successfully to {json_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save data to {json_path}: {e}")
            return False

    async def cleanup(self):
        """Clean up browser resources."""
        if self.browser:
            await self.browser.close()
            self.logger.info("Browser closed.")

    async def run(self):
        """Main execution function."""
        self.logger.info("Starting WindrawWin scraper...")
        async with async_playwright() as p:
            await self.setup_browser(p)
            matches = await self.scrape_matches()
            self.save_data(matches)
            await self.cleanup()
        self.logger.info("Scraping run finished.")


if __name__ == "__main__":
    scraper = EnhancedWindrawWinScraper()
    asyncio.run(scraper.run())
