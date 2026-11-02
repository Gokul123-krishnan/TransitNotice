import sqlite3
import datetime
from zoneinfo import ZoneInfo
from werkzeug.security import generate_password_hash
from config import Config

def format_dt(dt):
    """Formats datetime to standard ISO string YYYY-MM-DD HH:MM:SS in Asia/Kolkata timezone."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=Config.TIMEZONE)
    else:
        dt = dt.astimezone(Config.TIMEZONE)
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def parse_dt(dt_str):
    """Parses standard ISO string to timezone-aware datetime in Asia/Kolkata."""
    if not dt_str:
        return None
    if isinstance(dt_str, datetime.datetime):
        if dt_str.tzinfo is None:
            return dt_str.replace(tzinfo=Config.TIMEZONE)
        return dt_str.astimezone(Config.TIMEZONE)
    try:
        cleaned = dt_str.replace('T', ' ')
        if '.' in cleaned:
            cleaned = cleaned.split('.')[0]
        dt = datetime.datetime.strptime(cleaned, '%Y-%m-%d %H:%M:%S')
        return dt.replace(tzinfo=Config.TIMEZONE)
    except Exception:
        try:
            dt = datetime.datetime.strptime(dt_str[:10], '%Y-%m-%d')
            return dt.replace(tzinfo=Config.TIMEZONE)
        except Exception:
            return None

def get_now_ist():
    return datetime.datetime.now(Config.TIMEZONE)

def get_now_ist_str():
    return format_dt(get_now_ist())

def get_db():
    conn = sqlite3.connect(Config.DATABASE_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Agencies Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agencies (
        agency_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        authority_type TEXT NOT NULL,
        portal_url TEXT,
        contact_info TEXT
    )
    """)

    # 2. Bus Routes Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bus_routes (
        route_id TEXT PRIMARY KEY,
        route_number TEXT NOT NULL,
        origin TEXT NOT NULL,
        destination TEXT NOT NULL,
        key_stops TEXT NOT NULL,
        description TEXT,
        operating_agency TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'NORMAL',
        is_manual_override INTEGER NOT NULL DEFAULT 0,
        last_updated TEXT NOT NULL
    )
    """)

    # Migration: ensure is_manual_override column exists in bus_routes if table was already created
    cursor.execute("PRAGMA table_info(bus_routes)")
    col_names = [col['name'] if isinstance(col, sqlite3.Row) else col[1] for col in cursor.fetchall()]
    if 'is_manual_override' not in col_names:
        cursor.execute("ALTER TABLE bus_routes ADD COLUMN is_manual_override INTEGER NOT NULL DEFAULT 0")

    # 3. Bus Stops Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bus_stops (
        stop_id INTEGER PRIMARY KEY AUTOINCREMENT,
        stop_name TEXT NOT NULL,
        area_name TEXT NOT NULL,
        landmark TEXT,
        connecting_routes TEXT
    )
    """)

    # 4. Notices Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notices (
        notice_id TEXT PRIMARY KEY,
        agency TEXT NOT NULL,
        route_id TEXT NOT NULL,
        area TEXT NOT NULL,
        source_url TEXT,
        notice_type TEXT NOT NULL,
        summary TEXT NOT NULL,
        description TEXT,
        published_at TEXT NOT NULL,
        valid_from TEXT NOT NULL,
        valid_to TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        observed_at TEXT NOT NULL,
        last_confirmed_at TEXT NOT NULL,
        content_hash TEXT,
        revision_id INTEGER NOT NULL DEFAULT 1,
        change_summary TEXT,
        alert_status TEXT NOT NULL DEFAULT 'WARNING',
        alerted_at TEXT,
        is_sample INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (agency) REFERENCES agencies(agency_id)
    )
    """)

    # 5. Scraper Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scraper_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_name TEXT NOT NULL,
        url TEXT,
        checked_at TEXT NOT NULL,
        status TEXT NOT NULL,
        notices_found INTEGER DEFAULT 0,
        notices_added INTEGER DEFAULT 0,
        notices_updated INTEGER DEFAULT 0,
        error_message TEXT,
        response_time_ms INTEGER DEFAULT 0
    )
    """)

    # 6. Notice History Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notice_history (
        history_id INTEGER PRIMARY KEY AUTOINCREMENT,
        notice_id TEXT NOT NULL,
        revision_id INTEGER NOT NULL,
        change_type TEXT NOT NULL,
        old_data TEXT,
        new_data TEXT,
        change_notes TEXT,
        modified_by TEXT NOT NULL,
        modified_at TEXT NOT NULL,
        FOREIGN KEY (notice_id) REFERENCES notices(notice_id) ON DELETE CASCADE
    )
    """)

    # 7. Notifications Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
        notice_id TEXT,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        notification_type TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'INFO',
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)

    # 8. Admin Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'Transport Admin',
        last_login TEXT
    )
    """)

    # Indices for high performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notices_status ON notices(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notices_area ON notices(area)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notices_route ON notices(route_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notices_dates ON notices(valid_from, valid_to)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_notice_id ON notice_history(notice_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(is_read)")

    conn.commit()
    conn.close()

def seed_db():
    conn = get_db()
    cursor = conn.cursor()
    now_ist = get_now_ist()

    # 1. Seed Admin User
    cursor.execute("SELECT COUNT(*) FROM admin_users")
    if cursor.fetchone()[0] == 0:
        admin_pass_hash = generate_password_hash(Config.DEFAULT_ADMIN_PASS)
        cursor.execute("""
            INSERT INTO admin_users (username, password_hash, full_name, role, last_login)
            VALUES (?, ?, ?, ?, ?)
        """, (Config.DEFAULT_ADMIN_USER, admin_pass_hash, 'Salem City Transport Administrator', 'Super Admin', format_dt(now_ist)))

    # 2. Seed Agencies
    cursor.execute("SELECT COUNT(*) FROM agencies")
    if cursor.fetchone()[0] == 0:
        agencies_data = [
            (
                'TNSTC-SLM',
                'Tamil Nadu State Transport Corporation (Salem) Ltd.',
                'State Transit Corporation',
                'https://www.tnstc.in',
                'Ramakrishna Road, Salem - 636007 | Ph: 0427-2403241'
            ),
            (
                'SLM-TRAFFIC-POLICE',
                'Salem City Traffic Police',
                'Law Enforcement & Traffic Regulation',
                'https://salemcitypolice.tn.gov.in',
                'City Police Commissionerate, Salem - 636007 | Control Room: 0427-2212100'
            ),
            (
                'SLM-CORP-PWD',
                'Salem City Municipal Corporation (Engineering & Smart City)',
                'Urban Local Body / PWD',
                'https://salemcorporation.gov.in',
                'Corporation Main Office, Fort, Salem - 636001 | Toll Free: 1800-425-6360'
            )
        ]
        cursor.executemany("""
            INSERT INTO agencies (agency_id, name, authority_type, portal_url, contact_info)
            VALUES (?, ?, ?, ?, ?)
        """, agencies_data)

    # 3. Seed Verified Salem City Bus Routes
    cursor.execute("SELECT COUNT(*) FROM bus_routes")
    if cursor.fetchone()[0] == 0:
        routes_data = [
            (
                '1', 'Route 1', 'Salem Railway Junction', 'Salem Central (Old) Bus Stand',
                'Suramangalam, Leigh Bazaar, Four Roads, Old Bus Stand',
                'Prime heritage trunk corridor connecting railway hub to heart of the commercial city.',
                'TNSTC-SLM', 'NORMAL', format_dt(now_ist)
            ),
            (
                '13', 'Route 13', 'Salem New Bus Stand', 'Gorimedu',
                'New Bus Stand, Fairlands, Five Roads, Hasthampatti, Gorimedu (Govt Arts College)',
                'Key arterial route catering to students, IT corridor commuters and university wards.',
                'TNSTC-SLM', 'DIVERTED', format_dt(now_ist)
            ),
            (
                '14', 'Route 14', 'Salem Old Bus Stand', 'Omalur',
                'Old Bus Stand, New Bus Stand, Mamangam, Salem Tollgate, Omalur Bus Stand',
                'Northbound semi-urban express city service through national highway corridor.',
                'TNSTC-SLM', 'NORMAL', format_dt(now_ist)
            ),
            (
                '21', 'Route 21', 'Salem New Bus Stand', 'Salem Steel Plant',
                'New Bus Stand, Five Roads, Suramangalam, Junction Bypass, Kandhampatti, Mohan Nagar, Steel Plant',
                'Major industrial corridor transit connecting city center to Steel Authority of India township.',
                'TNSTC-SLM', 'NORMAL', format_dt(now_ist)
            ),
            (
                '23', 'Route 23', 'Salem Old Bus Stand', 'Kannankurichi',
                'Old Bus Stand, Hasthampatti, Chettichavadi, Kannankurichi (Mookaneri Lake)',
                'Suburban connector along the foothill residential tracts of Yercaud foothills.',
                'TNSTC-SLM', 'NORMAL', format_dt(now_ist)
            ),
            (
                '26', 'Route 26', 'Salem Old Bus Stand', 'Salem New Bus Stand',
                'Old Bus Stand, Collectorate, Four Roads, Swarnapuri, New Bus Stand',
                'High-frequency inter-terminal transit shuttle operating at 5-minute headways.',
                'TNSTC-SLM', 'NORMAL', format_dt(now_ist)
            ),
            (
                '33', 'Route 33', 'Salem Old Bus Stand', 'Suramangalam / Junction',
                'Old Bus Stand, Meyyanur, Five Roads, Suramangalam, Salem Junction',
                'Essential link traversing dense commercial centers via Five Roads flyover circle.',
                'TNSTC-SLM', 'DIVERTED', format_dt(now_ist)
            ),
            (
                '44', 'Route 44', 'Salem New Bus Stand', 'Ammapet',
                'New Bus Stand, Five Roads, Three Roads, Gugai, Old Bus Stand, Ammapet Colony',
                'Cross-city eastern connection reaching traditional handloom weaving clusters.',
                'TNSTC-SLM', 'SUSPENDED', format_dt(now_ist)
            ),
            (
                '54', 'Route 54', 'Salem Railway Junction', 'Ayothiyapattinam',
                'Salem Junction, Leigh Bazaar, Old Bus Stand, Ammapet, Udayapatty, Ayothiyapattinam',
                'East-west lifeline connecting western rail head with the eastern gateway junction.',
                'TNSTC-SLM', 'NORMAL', format_dt(now_ist)
            ),
            (
                '82', 'Route 82', 'Salem Old Bus Stand', 'Kondalampatti Bypass',
                'Old Bus Stand, Gugai, Dadagapatty, Trichy Main Road, Seelanaickenpatti, Kondalampatti',
                'Southern trunk feeder connecting to NH-44 highway transport hub.',
                'TNSTC-SLM', 'NORMAL', format_dt(now_ist)
            )
        ]
        cursor.executemany("""
            INSERT INTO bus_routes (route_id, route_number, origin, destination, key_stops, description, operating_agency, status, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, routes_data)

    # 4. Seed Verified Salem Bus Stops
    cursor.execute("SELECT COUNT(*) FROM bus_stops")
    if cursor.fetchone()[0] == 0:
        stops_data = [
            ('Salem Central Bus Stand (Old Bus Stand)', 'Town Area', 'Near Fort & Old Market', '1, 14, 23, 26, 33, 44, 54, 82'),
            ('Salem New Bus Stand (MGR Central)', 'Meyyanur', 'OMR / Five Roads Link', '13, 14, 21, 26, 33, 44'),
            ('Salem Railway Junction', 'Suramangalam', 'Railway Divisional HQ', '1, 21, 33, 54'),
            ('Five Roads (Ainthu Karadu)', 'Fairlands / Meyyanur', 'Major 5-way Junction & Flyover', '13, 21, 33, 44'),
            ('Hasthampatti Roundtana', 'Hasthampatti', 'Sub-registrar Office & Cherry Road', '13, 23, 26'),
            ('Ammapet Main Bus Stop', 'Ammapet', 'Near Weavers Colony & Sengunthar Hall', '44, 54'),
            ('Fairlands Signal', 'Fairlands', 'Brindavan Road Corner', '13, 21, 33'),
            ('Suramangalam Market', 'Suramangalam', 'Suramangalam Main Road', '1, 21, 33'),
            ('Gorimedu Government College', 'Gorimedu', 'Salem Arts College & RTO Ground', '13'),
            ('Kondalampatti Roundabout', 'Kondalampatti', 'NH-44 Bypass Hub', '82'),
            ('Salem Steel Plant Main Gate', 'Steel Plant', 'Mohan Nagar Township Entrance', '21'),
            ('Omalur Road Mamangam', 'Omalur Road', 'Opposite Sona College / Mamangam', '14')
        ]
        cursor.executemany("""
            INSERT INTO bus_stops (stop_name, area_name, landmark, connecting_routes)
            VALUES (?, ?, ?, ?)
        """, stops_data)

    # 5. Seed Demonstration / Initial Verified Notices
    cursor.execute("SELECT COUNT(*) FROM notices")
    if cursor.fetchone()[0] == 0:
        notices_data = [
            (
                'SLM-TR-2026-001',
                'SLM-TRAFFIC-POLICE',
                '13, 33',
                'Five Roads, Fairlands',
                'https://salemcitypolice.tn.gov.in/traffic-advisory-2026-042',
                'Route Diversion',
                'Drainage stormwater culvert replacement at Five Roads Junction; city buses diverted via Meyyanur Inner Ring Road.',
                'Due to urgent underground stormwater culvert replacement being executed by Salem Municipal Corporation near Five Roads Signal, regular city buses operating from New Bus Stand towards Hasthampatti and Junction (Routes 13 and 33) are diverted via Meyyanur Bypass and Sharada College Road. Commuters are advised to board at temporary boarding shelters erected near Meyyanur post office.',
                format_dt(now_ist - datetime.timedelta(days=1)),
                format_dt(now_ist - datetime.timedelta(days=1)),
                format_dt(now_ist + datetime.timedelta(days=4)),
                'ACTIVE',
                format_dt(now_ist - datetime.timedelta(hours=2)),
                format_dt(now_ist - datetime.timedelta(hours=1)),
                'hash-demo-001',
                2,
                'Revision 2: Diversion route extended till weekend due to concrete curing requirements.',
                'WARNING',
                format_dt(now_ist - datetime.timedelta(hours=6)),
                1 # Marked as demonstration sample
            ),
            (
                'SLM-TR-2026-002',
                'TNSTC-SLM',
                '44',
                'Ammapet, Old Bus Stand',
                'https://www.tnstc.in/press-release-salem-2026-118',
                'Temporary Cancellation',
                'Temporary suspension of Route 44 mid-day trips due to Ammapet underground drainage pipe laying work.',
                'Salem Corporation smart water supply pipe trenching is active along Ammapet Main Bazaar Road. Buses on Route 44 between 11:30 AM and 03:30 PM are temporarily halted. Morning and evening peak-hour services operate via direct bypass through Kitchipalayam. Full normal service expected after road surface restoration.',
                format_dt(now_ist - datetime.timedelta(hours=18)),
                format_dt(now_ist - datetime.timedelta(hours=18)),
                format_dt(now_ist + datetime.timedelta(days=2)),
                'ACTIVE',
                format_dt(now_ist - datetime.timedelta(hours=3)),
                format_dt(now_ist - datetime.timedelta(minutes=45)),
                'hash-demo-002',
                1,
                'Initial announcement by TNSTC Salem Commercial Dept.',
                'CRITICAL',
                format_dt(now_ist - datetime.timedelta(hours=12)),
                1 # Marked as demonstration sample
            ),
            (
                'SLM-TR-2026-003',
                'SLM-CORP-PWD',
                '14',
                'Omalur Road, Mamangam',
                'https://salemcorporation.gov.in/notices/pwd-flyover-inspection-2026',
                'Planned Maintenance',
                'Scheduled expansion joint repairs on Mamangam Flyover on Omalur Road; single-lane shuttle for buses.',
                'Periodic bridge structural safety inspection and expansion joint rubber pad replacement on Mamangam grade separator. TNSTC city buses operating on Route 14 (Old Bus Stand to Omalur) will experience minor 5 to 10 minute delays as traffic is channeled through the service lane. Heavy multi-axle commercial vehicles are rerouted.',
                format_dt(now_ist - datetime.timedelta(days=2)),
                format_dt(now_ist + datetime.timedelta(days=1)),
                format_dt(now_ist + datetime.timedelta(days=5)),
                'UPCOMING',
                format_dt(now_ist - datetime.timedelta(hours=5)),
                format_dt(now_ist - datetime.timedelta(hours=2)),
                'hash-demo-003',
                1,
                'Initial advisory from Salem Smart City Engineering division.',
                'INFO',
                format_dt(now_ist - datetime.timedelta(days=1)),
                1 # Marked as demonstration sample
            ),
            (
                'SLM-TR-2026-004',
                'TNSTC-SLM',
                '21',
                'Steel Plant, Kandhampatti',
                'https://www.tnstc.in/updates/salem-sp-restored-089',
                'Service Restoration',
                'Restoration of full regular bus frequency on Route 21 (New Bus Stand to Salem Steel Plant).',
                'Bitumen relaying work on the Junction Bypass to Kandhampatti Steel Plant arterial road has been completed ahead of schedule. All scheduled morning, shift-worker and evening trips on Route 21 have been restored to their standard timetable with immediate effect.',
                format_dt(now_ist - datetime.timedelta(days=3)),
                format_dt(now_ist - datetime.timedelta(days=3)),
                format_dt(now_ist - datetime.timedelta(days=1)),
                'RESTORED',
                format_dt(now_ist - datetime.timedelta(days=1)),
                format_dt(now_ist - datetime.timedelta(days=1)),
                'hash-demo-004',
                2,
                'Status updated to RESTORED following road clearance verification.',
                'RESOLVED',
                format_dt(now_ist - datetime.timedelta(days=1)),
                1 # Marked as demonstration sample
            ),
            (
                'SLM-TR-2026-005',
                'SLM-TRAFFIC-POLICE',
                '1, 26',
                'Hasthampatti, Collectorate',
                'https://salemcitypolice.tn.gov.in/archives/advisory-old-fest-2026',
                'Road Closure',
                'Temporary temple festival diversion near Sugavaneswarar Temple; diversion concluded and archived.',
                'Annual temple car festival diversion around Fort Town and Hasthampatti Cherry Road has concluded safely. Buses have returned to original routes.',
                format_dt(now_ist - datetime.timedelta(days=10)),
                format_dt(now_ist - datetime.timedelta(days=10)),
                format_dt(now_ist - datetime.timedelta(days=7)),
                'EXPIRED',
                format_dt(now_ist - datetime.timedelta(days=7)),
                format_dt(now_ist - datetime.timedelta(days=7)),
                'hash-demo-005',
                1,
                'Archived advisory after validity lapse.',
                'INFO',
                format_dt(now_ist - datetime.timedelta(days=10)),
                1 # Marked as demonstration sample
            )
        ]
        cursor.executemany("""
            INSERT INTO notices (
                notice_id, agency, route_id, area, source_url, notice_type,
                summary, description, published_at, valid_from, valid_to,
                status, observed_at, last_confirmed_at, content_hash,
                revision_id, change_summary, alert_status, alerted_at, is_sample
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, notices_data)

    # 6. Seed Notice History for multi-revision notices
    cursor.execute("SELECT COUNT(*) FROM notice_history")
    if cursor.fetchone()[0] == 0:
        history_data = [
            (
                'SLM-TR-2026-001', 1, 'CREATED',
                '{"status": "ACTIVE", "valid_to": "' + format_dt(now_ist + datetime.timedelta(days=2)) + '"}',
                '{"status": "ACTIVE", "valid_to": "' + format_dt(now_ist + datetime.timedelta(days=2)) + '"}',
                'Initial advisory issued for stormwater culvert repair at Five Roads.',
                'Salem City Traffic Police Inspector',
                format_dt(now_ist - datetime.timedelta(days=1))
            ),
            (
                'SLM-TR-2026-001', 2, 'EXTENDED',
                '{"valid_to": "' + format_dt(now_ist + datetime.timedelta(days=2)) + '"}',
                '{"valid_to": "' + format_dt(now_ist + datetime.timedelta(days=4)) + '"}',
                'Extended validity period by 48 hours for concrete curing at culvert crossing.',
                'Salem City Traffic Police Inspector',
                format_dt(now_ist - datetime.timedelta(hours=6))
            ),
            (
                'SLM-TR-2026-004', 1, 'CREATED',
                '{"status": "ACTIVE"}',
                '{"status": "ACTIVE"}',
                'Initial road work notice for Kandhampatti arterial road.',
                'TNSTC Salem Depot Manager',
                format_dt(now_ist - datetime.timedelta(days=3))
            ),
            (
                'SLM-TR-2026-004', 2, 'RESTORED',
                '{"status": "ACTIVE"}',
                '{"status": "RESTORED"}',
                'Road work finished ahead of time. Full Route 21 service restored.',
                'TNSTC Salem Depot Manager',
                format_dt(now_ist - datetime.timedelta(days=1))
            )
        ]
        cursor.executemany("""
            INSERT INTO notice_history (
                notice_id, revision_id, change_type, old_data, new_data,
                change_notes, modified_by, modified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, history_data)

    # 7. Seed Initial In-App Notifications
    cursor.execute("SELECT COUNT(*) FROM notifications")
    if cursor.fetchone()[0] == 0:
        notifications_data = [
            (
                'SLM-TR-2026-001',
                'Notice Extended: Five Roads Culvert Repair',
                'Advisory for Route 13 & 33 diversion has been extended until weekend due to road concrete curing.',
                'EXTENDED_INTERRUPTION', 'WARNING', 0, format_dt(now_ist - datetime.timedelta(hours=6))
            ),
            (
                'SLM-TR-2026-002',
                'Critical Alert: Route 44 Ammapet Mid-Day Suspension',
                'Mid-day trips halted due to water pipe trenching in Ammapet Bazaar road.',
                'CANCELLED_NOTICE', 'CRITICAL', 0, format_dt(now_ist - datetime.timedelta(hours=12))
            ),
            (
                'SLM-TR-2026-004',
                'Service Restored: Route 21 Steel Plant Corridor',
                'Full scheduled bus frequency has resumed on Route 21 via Kandhampatti.',
                'RESTORED_SERVICE', 'RESOLVED', 1, format_dt(now_ist - datetime.timedelta(days=1))
            )
        ]
        cursor.executemany("""
            INSERT INTO notifications (
                notice_id, title, message, notification_type, severity, is_read, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, notifications_data)

    # 8. Seed Initial Scraper Log
    cursor.execute("SELECT COUNT(*) FROM scraper_logs")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO scraper_logs (
                source_name, url, checked_at, status, notices_found,
                notices_added, notices_updated, error_message, response_time_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'TNSTC Salem Circulars & Salem District Traffic Portal',
            'https://salemcitypolice.tn.gov.in/traffic-bulletin',
            format_dt(now_ist - datetime.timedelta(minutes=30)),
            'SUCCESS', 5, 1, 1, None, 420
        ))

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    seed_db()
    print("Database cleanly initialized.")
