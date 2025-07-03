#!/usr/bin/env python3
"""
WindrawWin Predictions Scraper
Scrapes today's football match predictions from windrawwin.com
"""

import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import requests
from bs4 import BeautifulSoup


class WindrawWinScraper:
    """Main scraper class for windrawwin.com predictions"""
    
    def __init__(self):
        self.base_url = "https://www.windrawwin.com/predictions/today/"
        self.session = requests.Session()
        self.setup_session()
        self.setup_logging()
    
    def setup_session(self):
        """Configure requests session with proper headers"""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        ]
        
        self.session.headers.update({
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def fetch_page(self) -> Optional[BeautifulSoup]:
        """Fetch and parse the main predictions page"""
        try:
            self.logger.info(f"Fetching data from {self.base_url}")
            response = self.session.get(self.base_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            self.logger.info("Successfully fetched and parsed page")
            return soup
            
        except requests.RequestException as e:
            self.logger.error(f"Error fetching page: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error parsing page: {e}")
            return None
    
    def extract_teams(self, match_div: BeautifulSoup) -> List[str]:
        """Extract team names from match div"""
        teams = []
        team_divs = match_div.find_all('div', class_='wtmoblnk')
        
        for team_div in team_divs[:2]:  # Only take first 2
            team_name = team_div.get_text(strip=True)
            if team_name:
                teams.append(team_name)
        
        return teams
    
    def extract_form(self, match_div: BeautifulSoup, team_num: int) -> List[str]:
        """Extract team form (last 5 matches)"""
        class_name = 'wtl5contl' if team_num == 1 else 'wtl5contr'
        form_container = match_div.find('div', class_=class_name)
        
        if not form_container:
            return []
        
        form = []
        form_divs = form_container.find_all('div')
        
        for div in form_divs:
            if 'last5w' in div.get('class', []):
                form.append('W')
            elif 'last5d' in div.get('class', []):
                form.append('D')
            elif 'last5l' in div.get('class', []):
                form.append('L')
        
        return form[:5]  # Limit to 5 results
    
    def extract_fixture(self, match_div: BeautifulSoup) -> str:
        """Extract fixture information"""
        fixture_div = match_div.find('div', class_='wtdesklnk')
        return fixture_div.get_text(strip=True) if fixture_div else ""
    
    def extract_odds(self, match_div: BeautifulSoup) -> Dict[str, List[str]]:
        """Extract all odds information"""
        odds = {
            "1x2": [],
            "over_under": [],
            "btts": []
        }
        
        # Extract 1x2 odds
        odds_1x2 = match_div.find('div', class_='wtmo')
        if odds_1x2:
            odds_cells = odds_1x2.find_all('div', class_='wtocell')
            for cell in odds_cells:
                link = cell.find('a')
                if link:
                    odds["1x2"].append(link.get_text(strip=True))
        
        # Extract over/under odds
        odds_ou = match_div.find('div', class_='wtou')
        if odds_ou:
            odds_cells = odds_ou.find_all('div', class_='wtocell')
            for cell in odds_cells:
                link = cell.find('a')
                if link:
                    odds["over_under"].append(link.get_text(strip=True))
        
        # Extract BTTS odds
        odds_btts = match_div.find('div', class_='wtbt')
        if odds_btts:
            odds_cells = odds_btts.find_all('div', class_='wtocell')
            for cell in odds_cells:
                link = cell.find('a')
                if link:
                    odds["btts"].append(link.get_text(strip=True))
        
        return odds
    
    def extract_prediction(self, match_div: BeautifulSoup) -> str:
        """Extract prediction"""
        prediction_div = match_div.find('div', class_='wtprd')
        return prediction_div.get_text(strip=True) if prediction_div else ""
    
    def extract_score(self, match_div: BeautifulSoup) -> str:
        """Extract predicted score"""
        score_div = match_div.find('div', class_='wtsc')
        return score_div.get_text(strip=True) if score_div else ""
    
    def parse_match(self, match_div: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """Parse a single match div and extract all required data"""
        try:
            match_data = {
                "teams": self.extract_teams(match_div),
                "team1_form": self.extract_form(match_div, 1),
                "team2_form": self.extract_form(match_div, 2),
                "fixture": self.extract_fixture(match_div),
                "odds": self.extract_odds(match_div),
                "prediction": self.extract_prediction(match_div),
                "score": self.extract_score(match_div)
            }
            
            # Only return if we have essential data
            if match_data["teams"] and len(match_data["teams"]) >= 2:
                return match_data
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error parsing match: {e}")
            return None
    
    def scrape_matches(self) -> List[Dict[str, Any]]:
        """Main scraping function to get all today's matches"""
        soup = self.fetch_page()
        if not soup:
            return []
        
        matches = []
        match_divs = soup.find_all('div', class_='wttr')
        
        self.logger.info(f"Found {len(match_divs)} potential match divs")
        
        for match_div in match_divs:
            match_data = self.parse_match(match_div)
            if match_data:
                matches.append(match_data)
        
        self.logger.info(f"Successfully parsed {len(matches)} matches")
        return matches
    
    def save_data(self, matches: List[Dict[str, Any]]) -> bool:
        """Save matches data to JSON file"""
        try:
            # Get current working directory
            current_dir = os.getcwd()
            json_path = os.path.join(current_dir, 'today_matches.json')
            
            self.logger.info(f"Saving data to: {json_path}")
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(matches, f, indent=2, ensure_ascii=False)
            
            # Verify file was created
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
    
    def run(self):
        """Main execution function"""
        try:
            self.logger.info("Starting WindrawWin scraper...")
            self.logger.info(f"Working directory: {os.getcwd()}")
            
            # Add small delay to avoid being too aggressive
            time.sleep(random.uniform(1, 3))
            
            matches = self.scrape_matches()
            
            if matches:
                self.logger.info(f"Found {len(matches)} matches to save")
                success = self.save_data(matches)
                if success:
                    self.log_result(True, len(matches))
                    self.logger.info("✅ Scraping completed successfully")
                else:
                    self.log_result(False, error_msg="Failed to save data to file")
                    self.logger.error("❌ Failed to save data")
            else:
                self.logger.warning("No matches found")
                # Still create empty JSON file for consistency
                self.save_data([])
                self.log_result(False, error_msg="No matches found or parsing failed")
                
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self.logger.error(error_msg)
            self.log_result(False, error_msg=error_msg)
            # Create empty JSON on error
            try:
                self.save_data([])
            except:
                pass


def main():
    """Main entry point"""
    scraper = WindrawWinScraper()
    scraper.run()


if __name__ == "__main__":
    main()
