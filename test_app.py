import uuid
import pytest
import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo
from database import get_db, init_db, seed_db, format_dt, get_now_ist
from config import Config
from app import app
from services.notice_service import NoticeService
from services.notification_service import NotificationService
from services.scraping_service import ScrapingService
from scraper import TransitNoticeScraper

@pytest.fixture(autouse=True)
def setup_test_db():
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    with app.app_context():
        init_db()
        seed_db()

@pytest.fixture
def client():
    with app.test_client() as client:
        yield client

def test_database_tables_exist(client):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row['name'] for row in cursor.fetchall()]
    conn.close()

    expected_tables = [
        'notices', 'bus_routes', 'bus_stops', 'agencies',
        'scraper_logs', 'notice_history', 'notifications', 'admin_users'
    ]
    for table in expected_tables:
        assert table in tables, f"Table {table} must exist in the SQLite database"

def test_salem_city_exclusivity(client):
    """Verify that all seeded routes and stops are strictly in Salem."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT origin, destination, key_stops FROM bus_routes")
    routes = cursor.fetchall()
    
    # Check that forbidden cities are NOT present
    forbidden_cities = ['Chennai', 'Madurai', 'Coimbatore', 'Tiruchirappalli', 'Bangalore']
    for r in routes:
        combined = f"{r['origin']} {r['destination']} {r['key_stops']}"
        for city in forbidden_cities:
            assert city not in combined, f"Route contains out-of-scope city: {city}"
    
    conn.close()

def test_expired_notice_never_active(client):
    """Validation Rule: An expired notice must never appear as currently active."""
    conn = get_db()
    cursor = conn.cursor()
    now_ist = get_now_ist()
    past_date = format_dt(now_ist - datetime.timedelta(days=2))
    
    test_id = f"SLM-TEST-EXP-{uuid.uuid4().hex[:6]}"
    cursor.execute("""
        INSERT OR REPLACE INTO notices (
            notice_id, agency, route_id, area, source_url, notice_type,
            summary, description, published_at, valid_from, valid_to,
            status, observed_at, last_confirmed_at, content_hash,
            revision_id, alert_status, is_sample
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, 1, 'WARNING', 1)
    """, (
        test_id, 'TNSTC-SLM', '1', 'Suramangalam', 'https://tnstc.in', 'Route Diversion',
        'Test expired notice', 'Should be expired', past_date, past_date, past_date,
        past_date, past_date, 'hash-test'
    ))
    conn.commit()
    conn.close()

    # Trigger synchronization
    NoticeService.sync_route_and_notice_statuses()

    # Retrieve notice
    notice, _ = NoticeService.get_notice_by_id(test_id)
    assert notice is not None
    assert notice.effective_status == 'EXPIRED'
    assert notice.status == 'EXPIRED'

def test_notice_revision_tracking(client):
    """Verify that updating a notice records changes in notice_history and increments revision."""
    notice_id = 'SLM-TR-2026-001'
    notice_before, hist_before = NoticeService.get_notice_by_id(notice_id)
    initial_rev = notice_before.revision_id
    initial_hist_count = len(hist_before)

    now_ist = get_now_ist()
    new_valid_to = format_dt(now_ist + datetime.timedelta(days=10))
    success, msg = NoticeService.update_notice(notice_id, {
        'valid_to': new_valid_to,
        'summary': 'Stormwater culvert repair further extended by traffic police'
    }, modified_by='Test Administrator')

    assert success is True
    
    notice_after, hist_after = NoticeService.get_notice_by_id(notice_id)
    assert notice_after.revision_id == initial_rev + 1
    assert len(hist_after) == initial_hist_count + 1
    assert hist_after[0]['change_type'] == 'EXTENDED'

def test_duplicate_notification_prevention(client):
    """Verify that duplicate notifications within short time are prevented."""
    unique_id = f"SLM-DUP-{uuid.uuid4().hex[:8]}"
    res1, msg1 = NotificationService.create_notification(
        notice_id=unique_id,
        title='Duplicate Test Alert',
        message='Testing notification duplicate prevention',
        notification_type='NEW_NOTICE',
        severity='INFO'
    )
    assert res1 is True

    # Immediate second call with identical notice_id and type
    res2, msg2 = NotificationService.create_notification(
        notice_id=unique_id,
        title='Duplicate Test Alert',
        message='Testing notification duplicate prevention',
        notification_type='NEW_NOTICE',
        severity='INFO'
    )
    assert res2 is False
    assert "Duplicate notification prevented" in msg2

def test_scraper_cycle_execution(client):
    """Verify that scraper executes, logs results without throwing uncaught exceptions."""
    with patch.object(TransitNoticeScraper, 'is_allowed_by_robots', return_value=True):
        with patch.object(TransitNoticeScraper, 'fetch_page', return_value=(None, 12, "Simulated network isolation")):
            report = ScrapingService.execute_scrape_cycle(simulate_demo_if_offline=True)
            assert 'status' in report
            assert report['status'] in ['SUCCESS', 'WARNING']
            assert report['notices_found'] >= 1
            assert report['duration_ms'] >= 0

            logs = ScrapingService.get_recent_logs(limit=1)
            assert len(logs) >= 1
            assert logs[0]['source_name'] != ""

def test_flask_public_endpoints(client):
    # 1. Home Dashboard
    res = client.get('/')
    assert res.status_code == 200
    assert b'Salem City Transit Dashboard' in res.data
    assert b'Total Bus Notices' in res.data

    # 2. Bus Routes Catalog
    res = client.get('/routes')
    assert res.status_code == 200
    assert b'Salem City Bus Routes' in res.data
    assert b'Route 1' in res.data

    # 3. Route Search filter
    res = client.get('/routes?q=Steel+Plant')
    assert res.status_code == 200
    assert b'Route 21' in res.data

    # 4. Transit Notices Catalog
    res = client.get('/notices')
    assert res.status_code == 200
    assert b'Salem Bus Transit Notices' in res.data

    # 5. Filter notices by Salem area
    res = client.get('/notices?area=Five+Roads')
    assert res.status_code == 200
    assert b'Five Roads' in res.data

    # 6. Notice Details & Timeline
    res = client.get('/notices/SLM-TR-2026-001')
    assert res.status_code == 200
    assert b'Advisory Revision History' in res.data

    # 7. About Page
    res = client.get('/about')
    assert res.status_code == 200
    assert b'Strictly Restricted to Salem City Transit Network' in res.data

def test_admin_auth_and_dashboard(client):
    # Unauthenticated access to dashboard should redirect to login
    res = client.get('/admin/dashboard')
    assert res.status_code == 302
    assert '/admin/login' in res.headers['Location']

    # Admin Login POST with valid credentials
    login_res = client.post('/admin/login', data={
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert login_res.status_code == 200
    assert b'Transit Administration Control Center' in login_res.data

    # Admin Dashboard should now be accessible
    dash_res = client.get('/admin/dashboard')
    assert dash_res.status_code == 200
    assert b'Manage Transit Notices' in dash_res.data

def test_api_endpoints(client):
    # Stats API
    res = client.get('/api/stats')
    assert res.status_code == 200
    data = res.get_json()
    assert 'total_notices' in data
    assert 'active_alerts' in data

    # Notifications API
    res = client.get('/api/notifications')
    assert res.status_code == 200
    data = res.get_json()
    assert 'unread_count' in data
    assert 'notifications' in data
