#!/usr/bin/env python3
"""
WindrawWin Predictions Scraper using Playwright
Scrapes today's football match predictions from windrawwin.com with Cloudflare bypass
"""

import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import asyncio

from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError


class WindrawWinScraper:
    """Main scraper class for windrawwin.com predictions using Playwright"""
    
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
            # Use Chromium with stealth settings for better Cloudflare bypass
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
            
            # Create context with realistic settings
            context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                java_script_enabled=True,
                locale='en-US',
                timezone_id='America/New_York'
            )
            
            # Add stealth scripts to avoid detection
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
                
                # Add realistic delay between attempts
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(2, 5)
                    self.logger.info(f"Waiting {delay:.1f} seconds before retry...")
                    await asyncio.sleep(delay)
                
                # Navigate to the page with extended timeout
                response = await self.page.goto(
                    self.base_url,
                    wait_until='networkidle',
                    timeout=60000  # 60 second timeout
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
                
                # Wait for page to load completely
                await self.page.wait_for_load_state('domcontentloaded', timeout=30000)
                
                # Check if we're blocked by Cloudflare
                cloudflare_check = await self.page.locator('text=Checking your browser').count()
                if cloudflare_check > 0:
                    self.logger.info("Cloudflare challenge detected, waiting...")
                    await asyncio.sleep(15)  # Wait for Cloudflare to process
                    await self.page.wait_for_load_state('networkidle', timeout=30000)
                
                # Check for essential content
                matches_found = await self.page.locator('.wttr').count()
                if matches_found == 0:
                    self.logger.warning(f"No match elements found on attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        self.logger.warning("No matches found after all attempts")
                        return True  # Return True to continue with empty result
                
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
    
    async def extract_match_data(self, match_locator) -> Optional[Dict[str, Any]]:
        """Extract data from a single match element"""
        try:
            match_data = {
                "teams": [],
                "time": "",
                "league": "",
                "prediction": "",
                "confidence": "",
                "odds": {
                    "1x2": [],
                    "over_under": [],
                    "btts": []
                }
            }
            
            # Extract team names
            team_elements = match_locator.locator('.wtmoblnk')
            team_count = await team_elements.count()
            
            for i in range(min(team_count, 2)):
                team_name = await team_elements.nth(i).text_content()
                if team_name:
                    match_data["teams"].append(team_name.strip())
            
            # Extract time/fixture info
            fixture_element = match_locator.locator('.wtdesklnk')
            if await fixture_element.count() > 0:
                fixture_text = await fixture_element.text_content()
                if fixture_text:
                    match_data["time"] = fixture_text.strip()
            
            # Extract league info (if available)
            league_element = match_locator.locator('.wtcompet')
            if await league_element.count() > 0:
                league_text = await league_element.text_content()
                if league_text:
                    match_data["league"] = league_text.strip()
            
            # Extract prediction
            prediction_element = match_locator.locator('.wtprd')
            if await prediction_element.count() > 0:
                prediction_text = await prediction_element.text_content()
                if prediction_text:
                    match_data["prediction"] = prediction_text.strip()
            
            # Extract confidence (if available)
            confidence_element = match_locator.locator('.wtconf')
            if await confidence_element.count() > 0:
                confidence_text = await confidence_element.text_content()
                if confidence_text:
                    match_data["confidence"] = confidence_text.strip()
            
            # Extract 1x2 odds
            odds_1x2_element = match_locator.locator('.wtmo .wtocell a')
            odds_1x2_count = await odds_1x2_element.count()
            for i in range(odds_1x2_count):
                odds_text = await odds_1x2_element.nth(i).text_content()
                if odds_text:
                    match_data["odds"]["1x2"].append(odds_text.strip())
            
            # Extract over/under odds
            odds_ou_element = match_locator.locator('.wtou .wtocell a')
            odds_ou_count = await odds_ou_element.count()
            for i in range(odds_ou_count):
                odds_text = await odds_ou_element.nth(i).text_content()
                if odds_text:
                    match_data["odds"]["over_under"].append(odds_text.strip())
            
            # Extract BTTS odds
            odds_btts_element = match_locator.locator('.wtbt .wtocell a')
            odds_btts_count = await odds_btts_element.count()
            for i in range(odds_btts_count):
                odds_text = await odds_btts_element.nth(i).text_content()
                if odds_text:
                    match_data["odds"]["btts"].append(odds_text.strip())
            
            # Only return if we have essential data (at least teams)
            if len(match_data["teams"]) >= 2:
                return match_data
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error extracting match data: {e}")
            return None
    
    async def scrape_matches(self) -> List[Dict[str, Any]]:
        """Main scraping function to get all today's matches"""
        success = await self.fetch_page()
        if not success:
            return []
        
        matches = []
        
        try:
            # Find all match elements
            match_elements = self.page.locator('.wttr')
            match_count = await match_elements.count()
            
            self.logger.info(f"Found {match_count} potential match elements")
            
            for i in range(match_count):
                match_element = match_elements.nth(i)
                match_data = await self.extract_match_data(match_element)
                
                if match_data:
                    matches.append(match_data)
                    self.logger.debug(f"Extracted match: {match_data['teams']}")
            
            self.logger.info(f"Successfully extracted {len(matches)} matches")
            
        except Exception as e:
            self.logger.error(f"Error scraping matches: {e}")
        
        return matches
    
    def save_data(self, matches: List[Dict[str, Any]]) -> bool:
        """Save matches data to JSON file"""
        try:
            current_dir = os.getcwd()
            json_path = os.path.join(current_dir, 'today_matches.json')
            
            self.logger.info(f"Saving data to: {json_path}")
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(matches, f, indent=2, ensure_ascii=False)
            
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
            
            if success:
                log_entry = f"[{timestamp}] Success. Scraped {matches_count} matches.\n"
            else:
                log_entry = f"[{timestamp}] Failed. Reason: {error_msg}\n"
            
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
            self.logger.info("Starting WindrawWin scraper with Playwright...")
            self.logger.info(f"Working directory: {os.getcwd()}")
            
            # Setup browser
            async with async_playwright() as p:
                await self.setup_browser(p)
                
                # Add initial realistic delay
                initial_delay = random.uniform(3, 8)
                self.logger.info(f"Initial delay: {initial_delay:.1f} seconds")
                await asyncio.sleep(initial_delay)
                
                # Scrape matches
                matches = await self.scrape_matches()
                
                # Always save data (even if empty)
                success = self.save_data(matches)
                
                if success and matches:
                    self.log_result(True, len(matches))
                    self.logger.info("✅ Scraping completed successfully")
                elif success and not matches:
                    self.log_result(False, error_msg="No matches found or extracted")
                    self.logger.warning("⚠️ No matches found, but saved empty file")
                else:
                    self.log_result(False, error_msg="Failed to save data to file")
                    self.logger.error("❌ Failed to save data")
                
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self.logger.error(error_msg)
            self.log_result(False, error_msg=error_msg)
            
            # Try to save empty file on error
            try:
                self.save_data([])
            except:
                pass
        
        finally:
            await self.cleanup()


async def main():
    """Main entry point"""
    scraper = WindrawWinScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
