#!/usr/bin/env python3
"""
Enhanced WindrawWin Predictions Scraper using Playwright
Improved version with better data extraction and error handling
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
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--single-process',
                    '--disable-gpu',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-features=TranslateUI',
                    '--disable-ipc-flooding-protection',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
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
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });

                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });

                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });

                window.chrome = {
                    runtime: {},
                };

                Object.defineProperty(navigator, 'permissions', {
                    get: () => ({
                        query: () => Promise.resolve({ state: 'granted' }),
                    }),
                });
            """)

            self.page = await context.new_page()
            self.logger.info("Browser setup completed successfully")

        except Exception as e:
            self.logger.error(f"Error setting up browser: {e}")
            raise

    async def fetch_page(self) -> bool:
        """Fetch and load the main predictions page"""
        max_retries = 3
        base_delay = 10

        for attempt in range(max_retries):
            try:
                self.logger.info(f"Fetching data from {self.base_url} (attempt {attempt + 1}/{max_retries})")

                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(2, 5)
                    self.logger.info(f"Waiting {delay:.1f} seconds before retry...")
                    await asyncio.sleep(delay)

                response = await self.page.goto(
                    self.base_url,
                    wait_until='networkidle',
                    timeout=60000
                )

                if response:
                    self.logger.info(f"Response status: {response.status}")

                    if response.status == 403:
                        self.logger.warning(f"403 Forbidden on attempt {attempt + 1}")
                        if attempt < max_retries - 1:
                            continue
                        else:
                            raise Exception(f"403 Forbidden after {max_retries} attempts")

                    if response.status >= 400:
                        self.logger.warning(f"HTTP {response.status} on attempt {attempt + 1}")
                        if attempt < max_retries - 1:
                            continue
                        else:
                            raise Exception(f"HTTP {response.status} after {max_retries} attempts")

                await self.page.wait_for_load_state('domcontentloaded', timeout=30000)

                # Check for Cloudflare challenge
                cloudflare_check = await self.page.locator('text=Checking your browser').count()
                if cloudflare_check > 0:
                    self.logger.info("Cloudflare challenge detected, waiting...")
                    await asyncio.sleep(15)
                    await self.page.wait_for_load_state('networkidle', timeout=30000)

                # Check for essential content
                matches_found = await self.page.locator('.wttr').count()
                if matches_found == 0:
                    self.logger.warning(f"No match elements found on attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        self.logger.warning("No matches found after all attempts")
                        return True

                self.logger.info(f"Successfully loaded page with {matches_found} potential matches")
                return True

            except PlaywrightTimeoutError as e:
                self.logger.error(f"Timeout error on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise Exception(f"Timeout after {max_retries} attempts")
            except Exception as e:
                self.logger.error(f"Error on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise

        return False

    def clean_text(self, text: str) -> str:
        """Clean and normalize text content"""
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text.strip())

    def extract_league_from_fixture(self, fixture_text: str) -> str:
        """Extract league information from fixture text or URL"""
        if not fixture_text:
            return ""
        
        # This approach is more dynamic than a fixed list
        try:
            # Example URL: https://www.windrawwin.com/tips/iceland-urvalsdeild/afturelding...
            # We want to extract 'iceland-urvalsdeild'
            parts = fixture_text.split('/')
            if 'tips' in parts:
                league_part = parts[parts.index('tips') + 1]
                return league_part.replace('-', ' ').title()
        except (ValueError, IndexError):
            self.logger.warning(f"Could not dynamically extract league from URL: {fixture_text}")

        return "" # Return empty if dynamic extraction fails

    async def extract_match_data(self, match_locator) -> Optional[Dict[str, Any]]:
        """Extract data from a single match element with corrected positional logic"""
        try:
            match_data = {
                "teams": {"home": "", "away": ""},
                "fixture": "",
                "league": "",
                "prediction": {"type": "", "stake": "", "score": ""},
                "odds": {
                    "match_odds": {"home": "", "draw": "", "away": ""},
                    "over_under": {"over": "", "under": ""},
                    "btts": {"yes": "", "no": ""}
                },
                "form": {"home": [], "away": []},
                "has_odds": False,
                "match_url": ""
            }

            # --- Teams, Fixture, League, Prediction (These were mostly correct) ---
            home_team_loc = match_locator.locator('.wtteam .wtmoblnk').nth(0)
            away_team_loc = match_locator.locator('.wtteam .wtmoblnk').nth(1)
            match_data["teams"]["home"] = self.clean_text(await home_team_loc.text_content())
            match_data["teams"]["away"] = self.clean_text(await away_team_loc.text_content())

            fixture_element = match_locator.locator('.wtdesklnk')
            if await fixture_element.count() > 0:
                match_data["fixture"] = self.clean_text(await fixture_element.text_content())
                fixture_url = await fixture_element.get_attribute('href')
                if fixture_url:
                    match_data["match_url"] = fixture_url
                    match_data["league"] = self.extract_league_from_fixture(fixture_url)

            match_data["prediction"]["stake"] = self.clean_text(await match_locator.locator('.wtstk').text_content())
            match_data["prediction"]["type"] = self.clean_text(await match_locator.locator('.wtprd').text_content())
            match_data["prediction"]["score"] = self.clean_text(await match_locator.locator('.wtsc').text_content())

            # --- CORRECTED ODDS EXTRACTION ---
            match_data["has_odds"] = await match_locator.locator('.wtmo .wtocell a').count() > 0

            if match_data["has_odds"]:
                # Match Odds (1X2)
                odds_1x2_locs = match_locator.locator('.wtmo .wtocell a')
                if await odds_1x2_locs.count() >= 3:
                    match_data["odds"]["match_odds"]["home"] = self.clean_text(await odds_1x2_locs.nth(0).text_content())
                    match_data["odds"]["match_odds"]["draw"] = self.clean_text(await odds_1x2_locs.nth(1).text_content())
                    match_data["odds"]["match_odds"]["away"] = self.clean_text(await odds_1x2_locs.nth(2).text_content())

                # Over/Under 2.5 Odds
                odds_ou_locs = match_locator.locator('.wtou .wtocell a')
                if await odds_ou_locs.count() >= 2:
                    match_data["odds"]["over_under"]["over"] = self.clean_text(await odds_ou_locs.nth(0).text_content())
                    match_data["odds"]["over_under"]["under"] = self.clean_text(await odds_ou_locs.nth(1).text_content())

                # BTTS Odds
                odds_btts_locs = match_locator.locator('.wtbt .wtocell a')
                if await odds_btts_locs.count() >= 2:
                    match_data["odds"]["btts"]["yes"] = self.clean_text(await odds_btts_locs.nth(0).text_content())
                    match_data["odds"]["btts"]["no"] = self.clean_text(await odds_btts_locs.nth(1).text_content())

            # --- CORRECTED FORM EXTRACTION ---
            # Helper function to parse form items
            async def parse_form(form_locator):
                forms = []
                for i in range(await form_locator.count()):
                    item = form_locator.nth(i)
                    form_class = await item.get_attribute('class')
                    if 'last5w' in form_class: forms.append('W')
                    elif 'last5d' in form_class: forms.append('D')
                    elif 'last5l' in form_class: forms.append('L')
                return forms

            # Get home and away form using their specific container classes
            home_form_items = match_locator.locator('.wtl5contl > div')
            away_form_items = match_locator.locator('.wtl5contr > div')
            
            match_data["form"]["home"] = await parse_form(home_form_items)
            match_data["form"]["away"] = await parse_form(away_form_items)

            if match_data["teams"]["home"] and match_data["teams"]["away"]:
                return match_data
            return None

        except Exception as e:
            team_name = await match_locator.locator('.wtmoblnk').first.text_content()
            self.logger.error(f"Error extracting data for match starting with '{team_name}': {e}")
            return None


    async def scrape_matches(self) -> List[Dict[str, Any]]:
        """Main scraping function to get all today's matches"""
        success = await self.fetch_page()
        if not success:
            return []

        matches = []
        try:
            match_elements = self.page.locator('div.wdwtablest > div.wttr')
            match_count = await match_elements.count()
            self.logger.info(f"Found {match_count} potential match elements using specific selector.")

            for i in range(match_count):
                match_element = match_elements.nth(i)
                # Skip if it's not a real match row (sometimes headers or other elements can have similar classes)
                if await match_element.locator('.wtteam').count() == 0:
                    continue
                
                match_data = await self.extract_match_data(match_element)
                if match_data:
                    matches.append(match_data)
                    self.logger.debug(f"Extracted match: {match_data['teams']['home']} vs {match_data['teams']['away']}")

            self.logger.info(f"Successfully extracted {len(matches)} matches")

        except Exception as e:
            self.logger.error(f"Error scraping matches: {e}")

        return matches

    def save_data(self, matches: List[Dict[str, Any]]) -> bool:
        """Save matches data to JSON file with enhanced formatting"""
        try:
            current_dir = os.getcwd()
            json_path = os.path.join(current_dir, 'today_matches.json')

            summary_data = {
                "scrape_info": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "total_matches": len(matches),
                    "matches_with_odds": len([m for m in matches if m.get("has_odds", False)]),
                    "matches_without_odds": len([m for m in matches if not m.get("has_odds", False)]),
                    "source_url": self.base_url
                },
                "matches": matches
            }

            self.logger.info(f"Saving data to: {json_path}")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)

            if os.path.exists(json_path):
                file_size = os.path.getsize(json_path)
                self.logger.info(f"✅ Data saved successfully to {json_path} ({file_size} bytes, {len(matches)} matches)")
                return True
            else:
                self.logger.error(f"❌ File was not created at {json_path}")
                return False

        except Exception as e:
            self.logger.error(f"Error saving data: {e}")
            return False

    def log_result(self, success: bool, matches_count: int = 0, error_msg: str = ""):
        """Log scraping result to file"""
        try:
            current_dir = os.getcwd()
            log_path = os.path.join(current_dir, 'scrape_log.txt')
            timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M GMT')

            log_entry = f"[{timestamp}] {'Success' if success else 'Failed'}. "
            if success:
                log_entry += f"Scraped {matches_count} matches.\n"
            else:
                log_entry += f"Reason: {error_msg}\n"

            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            self.logger.info(f"Log entry added to {log_path}: {log_entry.strip()}")

        except Exception as e:
            self.logger.error(f"Error writing to log file: {e}")

    async def cleanup(self):
        """Clean up browser resources"""
        try:
            if self.browser:
                await self.browser.close()
                self.logger.info("Browser closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing browser: {e}")

    async def run(self):
        """Main execution function"""
        try:
            self.logger.info("Starting Enhanced WindrawWin scraper...")
            self.logger.info(f"Working directory: {os.getcwd()}")
            async with async_playwright() as p:
                await self.setup_browser(p)
                initial_delay = random.uniform(3, 8)
                self.logger.info(f"Initial delay: {initial_delay:.1f} seconds")
                await asyncio.sleep(initial_delay)

                matches = await self.scrape_matches()
                success = self.save_data(matches)

                if success and matches:
                    self.log_result(True, len(matches))
                    self.logger.info("✅ Enhanced scraping completed successfully")
                elif success and not matches:
                    self.log_result(False, error_msg="No matches found or extracted")
                    self.logger.warning("⚠️ No matches found, but saved empty file")
                else:
                    self.log_result(False, error_msg="Failed to save data to file")
                    self.logger.error("❌ Failed to save data")
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.log_result(False, error_msg=error_msg)
            try:
                self.save_data([]) # Attempt to save an empty file on catastrophic failure
            except:
                pass
        finally:
            await self.cleanup()


async def main():
    """Main entry point"""
    scraper = EnhancedWindrawWinScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
