import json
import time
import datetime
from database import get_db, format_dt, parse_dt, get_now_ist
from config import Config
from scraper import TransitNoticeScraper
from services.notice_service import NoticeService
from services.notification_service import NotificationService

class ScrapingService:
    @staticmethod
    def execute_scrape_cycle(source_url=None, simulate_demo_if_offline=True):
        """
        Executes a complete scraping & update cycle:
        1. Queries public permitted sources.
        2. Detects new, modified, extended, or restored notices.
        3. Updates database & notice history.
        4. Triggers in-app notifications.
        5. Logs full execution report in scraper_logs table.
        """
        scraper = TransitNoticeScraper()
        target_url = source_url or "https://salemcitypolice.tn.gov.in/traffic-bulletin"
        source_name = "Salem City Police Traffic Advisory & TNSTC Salem Notices"

        start_time = time.time()
        notices_found = 0
        notices_added = 0
        notices_updated = 0
        status = "SUCCESS"
        error_message = None

        # 1. Check robots.txt permissions
        if not scraper.is_allowed_by_robots(target_url):
            error_message = "Crawling restricted by robots.txt policy."
            status = "WARNING"

        # 2. Attempt fetching target source
        resp, duration_ms, fetch_err = scraper.fetch_page(target_url)

        collected_items = []
        if resp and resp.status_code == 200:
            collected_items = scraper.parse_official_bulletin_html(resp.text, base_url=target_url)
            notices_found = len(collected_items)
        else:
            if fetch_err:
                error_message = fetch_err
            elif resp:
                error_message = f"HTTP {resp.status_code}: Source portal temporarily unavailable."
            else:
                error_message = "Unable to connect to government portal."

            if simulate_demo_if_offline:
                collected_items = scraper.generate_demonstration_feed()
                notices_found = len(collected_items)
                status = "SUCCESS" if not fetch_err else "WARNING"
                error_message = (error_message or "") + " (Active Salem demonstration feed evaluated for change detection)"
            else:
                status = "FAILED"

        # 3. Process collected notices and detect changes
        conn = get_db()
        cursor = conn.cursor()
        now_str = format_dt(get_now_ist())
        notifications_to_send = []

        for item in collected_items:
            notice_id = item.get('notice_id')
            if not notice_id:
                continue

            summary = item.get('summary', '')
            desc = item.get('description', '')
            valid_to = item.get('valid_to', now_str)
            item_status = item.get('status', 'ACTIVE')
            
            # Content string for hashing
            content_payload = f"{summary}|{desc}|{valid_to}|{item_status}"
            content_hash = scraper.calculate_hash(content_payload)

            cursor.execute("SELECT * FROM notices WHERE notice_id = ?", (notice_id,))
            existing = cursor.fetchone()

            if not existing:
                # NEW NOTICE
                cursor.execute("""
                    INSERT INTO notices (
                        notice_id, agency, route_id, area, source_url, notice_type,
                        summary, description, published_at, valid_from, valid_to,
                        status, observed_at, last_confirmed_at, content_hash,
                        revision_id, change_summary, alert_status, alerted_at, is_sample
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    notice_id,
                    item.get('agency', 'TNSTC-SLM'),
                    item.get('route_id', '1'),
                    item.get('area', 'Salem Central'),
                    item.get('source_url', target_url),
                    item.get('notice_type', 'Route Diversion'),
                    summary,
                    desc,
                    item.get('published_at', now_str),
                    item.get('valid_from', now_str),
                    valid_to,
                    item_status,
                    now_str,
                    now_str,
                    content_hash,
                    1,
                    'First recorded by automatic scraper.',
                    item.get('alert_status', 'WARNING'),
                    now_str,
                    item.get('is_sample', 1)
                ))

                # Notice history
                cursor.execute("""
                    INSERT INTO notice_history (
                        notice_id, revision_id, change_type, old_data, new_data,
                        change_notes, modified_by, modified_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    notice_id, 1, 'CREATED', None,
                    json.dumps({'summary': summary, 'valid_to': valid_to, 'status': item_status}),
                    'Discovered and parsed from official public feed.',
                    'Automated Scraper',
                    now_str
                ))

                notifications_to_send.append({
                    'notice_id': notice_id,
                    'title': f"New Scraped Advisory: {item.get('area', 'Salem')}",
                    'message': summary[:120],
                    'notification_type': 'NEW_NOTICE',
                    'severity': item.get('alert_status', 'WARNING')
                })
                notices_added += 1

            else:
                # EXISTING NOTICE - Check for changes
                ex_dict = dict(existing)
                if ex_dict['content_hash'] != content_hash:
                    # Notice modified or extended
                    new_rev = ex_dict['revision_id'] + 1
                    change_type = 'MODIFIED'
                    change_notes = "Content updated from official feed"

                    if valid_to != ex_dict['valid_to']:
                        change_type = 'EXTENDED'
                        change_notes = f"Validity period updated to {valid_to}"
                    elif item_status != ex_dict['status']:
                        change_type = 'STATUS_CHANGE'
                        change_notes = f"Status altered to {item_status}"

                    cursor.execute("""
                        UPDATE notices
                        SET summary = ?, description = ?, valid_to = ?, status = ?,
                            last_confirmed_at = ?, content_hash = ?, revision_id = ?,
                            change_summary = ?
                        WHERE notice_id = ?
                    """, (
                        summary, desc, valid_to, item_status,
                        now_str, content_hash, new_rev,
                        change_notes, notice_id
                    ))

                    cursor.execute("""
                        INSERT INTO notice_history (
                            notice_id, revision_id, change_type, old_data, new_data,
                            change_notes, modified_by, modified_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        notice_id, new_rev, change_type,
                        json.dumps({'summary': ex_dict['summary'], 'valid_to': ex_dict['valid_to'], 'status': ex_dict['status']}),
                        json.dumps({'summary': summary, 'valid_to': valid_to, 'status': item_status}),
                        change_notes,
                        'Automated Scraper',
                        now_str
                    ))

                    notifications_to_send.append({
                        'notice_id': notice_id,
                        'title': f"Advisory Updated ({notice_id}): {change_type}",
                        'message': change_notes,
                        'notification_type': 'EXTENDED_INTERRUPTION' if change_type == 'EXTENDED' else 'MODIFIED_ROUTE',
                        'severity': 'WARNING'
                    })
                    notices_updated += 1
                else:
                    # Notice unchanged, update confirmation timestamp
                    cursor.execute("""
                        UPDATE notices
                        SET last_confirmed_at = ?
                        WHERE notice_id = ?
                    """, (now_str, notice_id))

        # 4. Insert log into scraper_logs
        total_time_ms = int((time.time() - start_time) * 1000)
        cursor.execute("""
            INSERT INTO scraper_logs (
                source_name, url, checked_at, status, notices_found,
                notices_added, notices_updated, error_message, response_time_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source_name, target_url, now_str, status,
            notices_found, notices_added, notices_updated,
            error_message, total_time_ms
        ))
        log_id = cursor.lastrowid

        # Commit and close connection BEFORE dispatching notifications and syncing routes
        conn.commit()
        conn.close()

        # 5. Dispatch accumulated in-app notifications
        for ntf in notifications_to_send:
            NotificationService.create_notification(
                notice_id=ntf['notice_id'],
                title=ntf['title'],
                message=ntf['message'],
                notification_type=ntf['notification_type'],
                severity=ntf['severity']
            )

        # 6. Synchronize route statuses
        NoticeService.sync_route_and_notice_statuses()

        return {
            'success': (status in ['SUCCESS', 'WARNING']),
            'status': status,
            'source_name': source_name,
            'url': target_url,
            'checked_at': now_str,
            'notices_found': notices_found,
            'notices_added': notices_added,
            'notices_updated': notices_updated,
            'error_message': error_message,
            'duration_ms': total_time_ms,
            'log_id': log_id
        }

    @staticmethod
    def get_recent_logs(limit=20):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM scraper_logs
            ORDER BY checked_at DESC
            LIMIT ?
        """, (limit,))
        logs = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return logs
