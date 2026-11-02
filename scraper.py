import hashlib
import time
import urllib.parse
import urllib.robotparser
import requests
from bs4 import BeautifulSoup
import datetime
from database import format_dt, parse_dt, get_now_ist
from config import Config

class TransitNoticeScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': Config.SCRAPER_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ta;q=0.8'
        })
        self.timeout = Config.SCRAPER_REQUEST_TIMEOUT
        self.max_retries = Config.SCRAPER_MAX_RETRIES

    def is_allowed_by_robots(self, target_url):
        """Checks if crawling the target URL is permitted by robots.txt."""
        try:
            parsed = urllib.parse.urlparse(target_url)
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(robots_url)
            
            # Fetch with short timeout
            resp = self.session.get(robots_url, timeout=3)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
                return rp.can_fetch(Config.SCRAPER_USER_AGENT, target_url)
            elif resp.status_code in [401, 403]:
                return False
            # 404 or other implies no restrictions
            return True
        except Exception:
            # If robots.txt cannot be fetched, default to courteous behavior
            return True

    def calculate_hash(self, content_str):
        """Generates SHA256 checksum for content change detection."""
        return hashlib.sha256(content_str.encode('utf-8')).hexdigest()

    def fetch_page(self, url):
        """Fetches a web page with retry mechanism and timeout handling."""
        start_time = time.time()
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                duration_ms = int((time.time() - start_time) * 1000)
                return resp, duration_ms, None
            except requests.exceptions.Timeout as e:
                if attempt == self.max_retries:
                    duration_ms = int((time.time() - start_time) * 1000)
                    return None, duration_ms, f"Request timed out after {self.timeout}s on {attempt} attempts: {str(e)}"
            except requests.exceptions.RequestException as e:
                duration_ms = int((time.time() - start_time) * 1000)
                return None, duration_ms, f"Connection error on attempt {attempt}: {str(e)}"
            time.sleep(1)
        duration_ms = int((time.time() - start_time) * 1000)
        return None, duration_ms, "Unknown fetch failure"

    def parse_official_bulletin_html(self, html_content, base_url="https://salemcitypolice.tn.gov.in"):
        """
        Parses official HTML structure looking for transit updates, diversions,
        and bus route advisories for Salem City.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        notices = []

        # Look for table rows, advisory cards, or article containers
        items = soup.find_all(['article', 'div'], class_=lambda c: c and any(k in c.lower() for k in ['notice', 'bulletin', 'advisory', 'transit', 'item']))
        
        # If no specialized classes, parse tables
        if not items:
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows[1:]:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) >= 4:
                        title = cols[0].get_text(strip=True)
                        desc = cols[1].get_text(strip=True)
                        date_str = cols[2].get_text(strip=True)
                        status_str = cols[3].get_text(strip=True)
                        if any(salem_loc in (title + desc) for salem_loc in ['Salem', 'Five Roads', 'Hasthampatti', 'Bus Stand', 'Suramangalam', 'Ammapet']):
                            notices.append({
                                'title': title,
                                'description': desc,
                                'date': date_str,
                                'status': status_str,
                                'source_url': base_url
                            })

        for item in items:
            title_tag = item.find(['h2', 'h3', 'h4', 'strong', 'a'])
            desc_tag = item.find('p')
            date_tag = item.find(['time', 'span'], class_=lambda c: c and 'date' in c.lower())

            title = title_tag.get_text(strip=True) if title_tag else "Transit Advisory"
            desc = desc_tag.get_text(strip=True) if desc_tag else ""
            date_val = date_tag.get_text(strip=True) if date_tag else format_dt(get_now_ist())
            link = title_tag.get('href') if title_tag and title_tag.name == 'a' else base_url

            # Filter exclusively for Salem city locations
            text_full = f"{title} {desc}"
            if any(k.lower() in text_full.lower() for k in ['salem', 'new bus stand', 'old bus stand', 'five roads', 'hasthampatti', 'suramangalam', 'ammapet', 'fairlands', 'kondalampatti', 'steel plant', 'omalur']):
                notices.append({
                    'title': title,
                    'description': desc or title,
                    'date': date_val,
                    'status': 'ACTIVE',
                    'source_url': link
                })

        return notices

    def generate_demonstration_feed(self, cycle=0):
        """
        Provides verified Salem-compliant demonstration data feed to safely
        test change detection, revision bumping, and notifications when live
        external government servers are offline or unconfigured.
        All entries are explicitly flagged with is_sample=1.
        """
        now = get_now_ist()
        return [
            {
                'notice_id': 'SLM-SCRAPE-001',
                'agency': 'SLM-TRAFFIC-POLICE',
                'route_id': '13, 33',
                'area': 'Five Roads, Meyyanur',
                'source_url': 'https://salemcitypolice.tn.gov.in/bulletin/stormwater-phase2',
                'notice_type': 'Route Diversion',
                'summary': 'Five Roads Flyover below surface storm culvert laying; buses shifted to Sharada College Road.',
                'description': 'Salem City Traffic Police Advisory Ref 102/2026: Due to Corporation stormwater pipeline work at 5 Roads junction, regular city buses 13 and 33 will use Sharada College link road till completion.',
                'published_at': format_dt(now - datetime.timedelta(days=1)),
                'valid_from': format_dt(now - datetime.timedelta(days=1)),
                'valid_to': format_dt(now + datetime.timedelta(days=3)),
                'status': 'ACTIVE',
                'alert_status': 'WARNING',
                'is_sample': 1
            },
            {
                'notice_id': 'SLM-SCRAPE-002',
                'agency': 'TNSTC-SLM',
                'route_id': '1',
                'area': 'Suramangalam, Leigh Bazaar',
                'source_url': 'https://www.tnstc.in/salem-junction-roadwork',
                'notice_type': 'Service Interruption',
                'summary': 'Railway goods yard road bitumen resurfacing; Route 1 buses delayed by 10 minutes at peak hours.',
                'description': 'Suramangalam Main Road railway crossing resurfacing is in progress. TNSTC Route 1 trips between Salem Junction and Old Bus Stand will operate with 10-minute headway padding.',
                'published_at': format_dt(now - datetime.timedelta(hours=6)),
                'valid_from': format_dt(now - datetime.timedelta(hours=6)),
                'valid_to': format_dt(now + datetime.timedelta(days=2)),
                'status': 'ACTIVE',
                'alert_status': 'INFO',
                'is_sample': 1
            },
            {
                'notice_id': 'SLM-SCRAPE-003',
                'agency': 'SLM-CORP-PWD',
                'route_id': '23',
                'area': 'Hasthampatti, Kannankurichi',
                'source_url': 'https://salemcorporation.gov.in/mookaneri-bridge-works',
                'notice_type': 'Planned Maintenance',
                'summary': 'Mookaneri Lake approach culvert safety inspection; Route 23 buses operating via Cherry Road.',
                'description': 'Routine structural check on culvert along foothill stretch of Kannankurichi. Buses operate normally with caution through single lane.',
                'published_at': format_dt(now - datetime.timedelta(hours=14)),
                'valid_from': format_dt(now + datetime.timedelta(hours=10)),
                'valid_to': format_dt(now + datetime.timedelta(days=4)),
                'status': 'UPCOMING',
                'alert_status': 'INFO',
                'is_sample': 1
            }
        ]
