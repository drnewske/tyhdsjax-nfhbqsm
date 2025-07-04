#!/usr/bin/env python3
"""
Enhanced WindrawWin Predictions Scraper using Playwright
Fixed version with precise odds extraction using positional awareness
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
        
        # Remove extra whitespace and normalize
        text = re.sub(r'\s+', ' ', text.strip())
        # Remove HTML entities
        text = text.replace('&nbsp;', '').replace('&amp;', '&')
        return text
    
    def extract_league_from_fixture(self, fixture_text: str) -> str:
        """Extract league information from fixture text or URL"""
        if not fixture_text:
            return ""
        
        # Common league patterns
        league_patterns = [
            r'finland-ykkonen',
            r'finland-kakkonen', 
            r'uzbekistan-super-league',
            r'club-world-cup',
            r'ireland-premier-division',
            r'england-premier-league',
            r'spain-la-liga',
            r'germany-bundesliga',
            r'italy-serie-a',
            r'france-ligue-1'
        ]
        
        for pattern in league_patterns:
            if re.search(pattern, fixture_text, re.IGNORECASE):
                return pattern.replace('-', ' ').title()
        
        return ""
    
    async def extract_match_data(self, match_locator) -> Optional[Dict[str, Any]]:
        """Extract data from a single match element with enhanced parsing"""
        try:
            match_data = {
                "teams": {
                    "home": "",
                    "away": ""
                },
                "fixture": "",
                "league": "",
                "prediction": {
                    "type": "",
                    "stake": "",
                    "score": ""
                },
                "odds": {
                    "match_odds": {
                        "home": "",
                        "draw": "",
                        "away": ""
                    },
                    "over_under": {
                        "over": "",
                        "under": ""
                    },
                    "btts": {
                        "yes": "",
                        "no": ""
                    }
                },
                "form": {
                    "home": [],
                    "away": []
                },
                "has_odds": False,
                "match_url": ""
            }
            
            # Extract team names
            team_elements = match_locator.locator('.wtmoblnk')
            team_count = await team_elements.count()
            
            if team_count >= 2:
                home_team = await team_elements.nth(0).text_content()
                away_team = await team_elements.nth(1).text_content()
                
                if home_team and away_team:
                    match_data["teams"]["home"] = self.clean_text(home_team)
                    match_data["teams"]["away"] = self.clean_text(away_team)
                else:
                    return None
            else:
                return None
            
            # Extract fixture info and URL
            fixture_element = match_locator.locator('.wtdesklnk')
            if await fixture_element.count() > 0:
                fixture_text = await fixture_element.text_content()
                fixture_url = await fixture_element.get_attribute('href')
                
                if fixture_text:
                    match_data["fixture"] = self.clean_text(fixture_text)
                
                if fixture_url:
                    match_data["match_url"] = fixture_url
                    match_data["league"] = self.extract_league_from_fixture(fixture_url)
            
            # Extract prediction details
            stake_element = match_locator.locator('.wtstk')
            if await stake_element.count() > 0:
                stake_text = await stake_element.text_content()
                if stake_text:
                    match_data["prediction"]["stake"] = self.clean_text(stake_text)
            
            prediction_element = match_locator.locator('.wtprd')
            if await prediction_element.count() > 0:
                prediction_text = await prediction_element.text_content()
                if prediction_text:
                    match_data["prediction"]["type"] = self.clean_text(prediction_text)
            
            score_element = match_locator.locator('.wtsc')
            if await score_element.count() > 0:
                score_text = await score_element.text_content()
                if score_text:
                    match_data["prediction"]["score"] = self.clean_text(score_text)
            
            # FIXED ODDS EXTRACTION - Using positional awareness
            # All odds are in .wtocell elements, but in specific order
            all_odds_elements = match_locator.locator('.wtocell a')
            odds_count = await all_odds_elements.count()
            
            self.logger.debug(f"Found {odds_count} odds elements for {match_data['teams']['home']} vs {match_data['teams']['away']}")
            
            if odds_count >= 7:  # Should have 7 odds total (3 + 2 + 2)
                match_data["has_odds"] = True
                
                # Extract 1X2 odds (positions 0, 1, 2)
                try:
                    home_odds = await all_odds_elements.nth(0).text_content()
                    draw_odds = await all_odds_elements.nth(1).text_content()
                    away_odds = await all_odds_elements.nth(2).text_content()
                    
                    if home_odds:
                        match_data["odds"]["match_odds"]["home"] = self.clean_text(home_odds)
                    if draw_odds:
                        match_data["odds"]["match_odds"]["draw"] = self.clean_text(draw_odds)
                    if away_odds:
                        match_data["odds"]["match_odds"]["away"] = self.clean_text(away_odds)
                    
                    self.logger.debug(f"1X2 odds: {home_odds} | {draw_odds} | {away_odds}")
                except Exception as e:
                    self.logger.warning(f"Error extracting 1X2 odds: {e}")
                
                # Extract Over/Under odds (positions 3, 4)
                try:
                    over_odds = await all_odds_elements.nth(3).text_content()
                    under_odds = await all_odds_elements.nth(4).text_content()
                    
                    if over_odds:
                        match_data["odds"]["over_under"]["over"] = self.clean_text(over_odds)
                    if under_odds:
                        match_data["odds"]["over_under"]["under"] = self.clean_text(under_odds)
                    
                    self.logger.debug(f"O/U odds: {over_odds} | {under_odds}")
                except Exception as e:
                    self.logger.warning(f"Error extracting O/U odds: {e}")
                
                # Extract BTTS odds (positions 5, 6)
                try:
                    btts_yes = await all_odds_elements.nth(5).text_content()
                    btts_no = await all_odds_elements.nth(6).text_content()
                    
                    if btts_yes:
                        match_data["odds"]["btts"]["yes"] = self.clean_text(btts_yes)
                    if btts_no:
                        match_data["odds"]["btts"]["no"] = self.clean_text(btts_no)
                    
                    self.logger.debug(f"BTTS odds: {btts_yes} | {btts_no}")
                except Exception as e:
                    self.logger.warning(f"Error extracting BTTS odds: {e}")
            
            else:
                self.logger.warning(f"Expected 7 odds elements, found {odds_count}")
                # Try alternative approach - look for specific containers
                
                # Try extracting from specific sections
                try:
                    # Match odds from .wtmo section
                    match_odds_section = match_locator.locator('.wtmo .wtocell a')
                    mo_count = await match_odds_section.count()
                    if mo_count >= 3:
                        match_data["odds"]["match_odds"]["home"] = self.clean_text(await match_odds_section.nth(0).text_content())
                        match_data["odds"]["match_odds"]["draw"] = self.clean_text(await match_odds_section.nth(1).text_content())
                        match_data["odds"]["match_odds"]["away"] = self.clean_text(await match_odds_section.nth(2).text_content())
                        self.logger.debug(f"Match odds via .wtmo: {mo_count} found")
                    
                    # Over/Under from .wtou section  
                    ou_section = match_locator.locator('.wtou .wtocell a')
                    ou_count = await ou_section.count()
                    if ou_count >= 2:
                        match_data["odds"]["over_under"]["over"] = self.clean_text(await ou_section.nth(0).text_content())
                        match_data["odds"]["over_under"]["under"] = self.clean_text(await ou_section.nth(1).text_content())
                        self.logger.debug(f"O/U odds via .wtou: {ou_count} found")
                    
                    # BTTS from .wtbt section
                    btts_section = match_locator.locator('.wtbt .wtocell a')
                    btts_count = await btts_section.count()
                    if btts_count >= 2:
                        match_data["odds"]["btts"]["yes"] = self.clean_text(await btts_section.nth(0).text_content())
                        match_data["odds"]["btts"]["no"] = self.clean_text(await btts_section.nth(1).text_content())
                        self.logger.debug(f"BTTS odds via .wtbt: {btts_count} found")
                    
                    # Set has_odds if any odds were found
                    if mo_count >= 3 or ou_count >= 2 or btts_count >= 2:
                        match_data["has_odds"] = True
                        
                except Exception as e:
                    self.logger.warning(f"Error in alternative odds extraction: {e}")
            
            # Extract team form (last 5 results)
            try:
                # Look for form in both left and right containers
                form_elements = match_locator.locator('.wtl5contl .last5w, .wtl5contl .last5d, .wtl5contl .last5l, .wtl5contr .last5w, .wtl5contr .last5d, .wtl5contr .last5l')
                form_count = await form_elements.count()
                
                if form_count >= 5:
                    # First 5 are home team form
                    for i in range(min(5, form_count)):
                        form_class = await form_elements.nth(i).get_attribute('class')
                        if form_class:
                            if 'last5w' in form_class:
                                match_data["form"]["home"].append('W')
                            elif 'last5d' in form_class:
                                match_data["form"]["home"].append('D')
                            elif 'last5l' in form_class:
                                match_data["form"]["home"].append('L')
                
                if form_count >= 10:
                    # Next 5 are away team form
                    for i in range(5, min(10, form_count)):
                        form_class = await form_elements.nth(i).get_attribute('class')
                        if form_class:
                            if 'last5w' in form_class:
                                match_data["form"]["away"].append('W')
                            elif 'last5d' in form_class:
                                match_data["form"]["away"].append('D')
                            elif 'last5l' in form_class:
                                match_data["form"]["away"].append('L')
            
            except Exception as e:
                self.logger.warning(f"Error extracting team form: {e}")
            
            # Only return if we have essential data
            if match_data["teams"]["home"] and match_data["teams"]["away"]:
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
            
            # Create summary data
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
            self.logger.info("Starting Enhanced WindrawWin scraper...")
            self.logger.info(f"Working directory: {os.getcwd()}")
            
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
                    self.logger.info("✅ Enhanced scraping completed successfully")
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
    scraper = EnhancedWindrawWinScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
