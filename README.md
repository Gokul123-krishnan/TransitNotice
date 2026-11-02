# TransitNotice – Salem City Bus Transit Update Tracker

A responsive web application designed exclusively for **Salem City, Tamil Nadu, India**, dedicated to tracking public transit service advisories, bus route diversions, temporary trip cancellations, planned road maintenance, and service restorations.

TransitNotice focuses strictly on Salem's city bus transit network operated by the **Tamil Nadu State Transport Corporation (Salem) Ltd. (TNSTC Salem City Division)** in coordination with the **Salem City Traffic Police** and **Salem City Municipal Corporation**.

---

## Key Highlights

- **Strict Salem City Focus**: Restricts transit advisories and bus corridors exclusively to Salem City. Cities such as Chennai, Coimbatore, and Madurai are excluded to provide hyper-localized, reliable passenger intelligence.
- **Official Source Attribution**: Every advisory attributes the issuing regulatory authority, includes direct official links, and displays automated verification timestamps in **Asia/Kolkata (IST)**.
- **No Fabricated GPS / Fake Tracking**: Focuses purely on verified public service announcements, road closures, and diversion notices without misleading real-time tracking simulations.
- **Cryptographic Change Detection**: Employs SHA-256 content hashing to detect updates, extensions, and restorations, maintaining a transparent audit trail of notice revisions.
- **Stale Notice Protection**: Any notice unverified for more than 48 hours is highlighted with a staleness warning, and overdue notices are expired automatically.
- **In-App Commuter Notifications**: Real-time alert tray with unread badge counter and duplicate notification suppression.
- **Administrative Control Center**: Secure transport officer portal with notice publishing, revision history inspection, bus route management, and manual scraper execution.

---

## Technology Stack

- **Frontend**: HTML5, CSS3, JavaScript (ES6+), Bootstrap 5.3, Font Awesome 6.5, Google Fonts (Inter)
- **Theme**: Navy Blue (`#0f172a`, `#1e293b`) & Vibrant Cyan (`#0891b2`, `#06b6d4`)
- **Backend**: Python 3.10+ / Flask Framework
- **Database**: SQLite3 with Write-Ahead Logging (WAL) and foreign key constraints
- **Web Scraping**: Python Requests & BeautifulSoup4 with `robots.txt` compliance, timeouts, and retry mechanisms
- **Task Scheduling**: APScheduler (Background periodic refresh every 15 minutes)
- **Timezone**: `Asia/Kolkata` (IST, UTC+05:30)

---

## Salem City Coverage Areas & Transit Hubs

TransitNotice covers prime bus hubs across Salem:
- **Salem Central Bus Stand (Old Bus Stand)**: Heritage hub connecting town market, Fort, and commercial quarters.
- **Salem New Bus Stand (MGR Central Bus Stand)**: Prime terminal on Omalur Main Road / Meyyanur link.
- **Salem Railway Junction / Suramangalam**: Western gateway and railway divisional terminal.
- **Five Roads (Ainthu Karadu)**: Arterial flyover junction linking Fairlands, Meyyanur, and Junction.
- **Hasthampatti Roundtana**: Cherry Road and Yercaud foothill junction.
- **Fairlands & Brindavan Road**: Commercial and shopping sectors.
- **Ammapet & Weavers Colony**: Traditional eastern textile and residential hub.
- **Kondalampatti Bypass**: Southern NH-44 highway interchange.
- **Gorimedu (Government Arts College)**: Northern educational corridor.
- **Salem Steel Plant (Mohan Nagar)**: Industrial township corridor.
- **Omalur Road & Mamangam**: Northern arterial highway stretch.

---

## Database Architecture (8 SQLite Tables)

The SQLite database (`instance/transitnotice.db`) is structured with eight relational tables:

1. **`notices`**: Primary advisory records (`notice_id`, `agency`, `route_id`, `area`, `source_url`, `notice_type`, `summary`, `description`, `published_at`, `valid_from`, `valid_to`, `status`, `observed_at`, `last_confirmed_at`, `content_hash`, `revision_id`, `change_summary`, `alert_status`, `alerted_at`, `is_sample`).
2. **`bus_routes`**: Verified Salem city bus routes (`route_id`, `route_number`, `origin`, `destination`, `key_stops`, `description`, `operating_agency`, `status`, `last_updated`).
3. **`bus_stops`**: Major bus stops across Salem City (`stop_id`, `stop_name`, `area_name`, `landmark`, `connecting_routes`).
4. **`agencies`**: Transport regulatory authorities (`agency_id`, `name`, `authority_type`, `portal_url`, `contact_info`).
5. **`scraper_logs`**: Audit trail of every automated and manual scraping cycle (`log_id`, `source_name`, `url`, `checked_at`, `status`, `notices_found`, `notices_added`, `notices_updated`, `error_message`, `response_time_ms`).
6. **`notice_history`**: Chronological revision history whenever a notice is modified or extended (`history_id`, `notice_id`, `revision_id`, `change_type`, `old_data`, `new_data`, `change_notes`, `modified_by`, `modified_at`).
7. **`notifications`**: In-app commuter alert items (`notification_id`, `notice_id`, `title`, `message`, `notification_type`, `severity`, `is_read`, `created_at`).
8. **`admin_users`**: Transport administrative credentials with hashed passwords (`user_id`, `username`, `password_hash`, `full_name`, `role`, `last_login`).

---

## Project Folder Structure

```
TransitNotice/
│
├── app.py                      # Flask Application server and routing logic
├── database.py                 # SQLite database schema, initialization, and seeding
├── scraper.py                  # Requests & BeautifulSoup web scraper with robots.txt parser
├── scheduler.py                # APScheduler background periodic sync job
├── config.py                   # Configuration, Salem boundary areas, and IST timezone
├── requirements.txt            # Python dependencies
├── test_app.py                 # Pytest test suite covering all modules
│
├── models/
│   └── notice_model.py         # Domain models for Notice, BusRoute, and BusStop
│
├── services/
│   ├── notice_service.py       # Query filtering, route status sync, revision tracking
│   ├── scraping_service.py     # Scraper orchestration, SHA256 change detection, logging
│   └── notification_service.py # In-app notification creation, deduplication, read APIs
│
├── templates/
│   ├── base.html               # Shared layout, navbar with live clock, sidebar, notification bell
│   ├── index.html              # Home Dashboard with metrics, alert banner, active notices
│   ├── routes.html             # Verified Salem bus routes catalog & stops directory
│   ├── notices.html            # Transit notices with multi-criteria search & filters
│   ├── notice_details.html     # Notice deep-dive, official source attribution, revision audit trail
│   ├── about.html              # Mission, Salem coverage, scraper ethics, agency contacts
│   ├── admin_login.html        # Secure transport officer authentication
│   └── admin_dashboard.html    # Notice CRUD, route status management, scraper logs, test broadcaster
│
├── static/
│   ├── css/
│   │   └── style.css           # Navy blue & cyan theme, glassmorphic cards, timelines
│   ├── js/
│   │   └── script.js           # Live clock in IST, notification tray AJAX, mobile toggle
│   └── images/
│       └── bus-icon.svg        # Transit emblem asset
│
├── instance/
│   └── transitnotice.db        # SQLite database
│
└── README.md                   # Documentation and run instructions
```

---

## Installation & Running Instructions

### 1. Prerequisites
- Python 3.10, 3.11, 3.12, or 3.13 installed
- Visual Studio Code or any modern code editor / terminal

### 2. Set Up Virtual Environment

Open Visual Studio Code terminal in the project directory (`TransitNotice`):

```powershell
# Create Python virtual environment
python -m venv venv

# Activate virtual environment on Windows
venv\Scripts\activate

# (On Linux / macOS: source venv/bin/activate)
```

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 4. Initialize Database & Seed Verified Salem Transit Data

```powershell
python database.py
```

### 5. Launch Application

```powershell
python app.py
```

Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## Admin Portal Access

- **Login URL**: `http://127.0.0.1:5000/admin/login`
- **Default Username**: `admin`
- **Default Password**: `admin123`

The administrative portal allows you to:
1. Publish new Salem transit notices with validation and source attribution.
2. Edit existing notices and extend validity dates (which automatically records a revision in `notice_history`).
3. Delete notices with confirmation.
4. Manually override or adjust bus route statuses (Normal, Diverted, Suspended).
5. Trigger an instant manual scraper refresh cycle and inspect historical audit logs.
6. Test in-application commuter alert broadcasts.

---

## Running the Automated Test Suite

A complete test suite is provided in `test_app.py` covering database tables, Salem city exclusivity, expiration rules, revision tracking, duplicate notification prevention, scraper execution, and all Flask endpoints:

```powershell
pytest test_app.py -v
```

All 9 test suites will run and pass cleanly.

---

## License & Attribution

Developed for Salem City public transport users. Built with Python Flask, SQLite, and Bootstrap 5. Official data attributed to TNSTC Salem Division and Salem City Traffic Police.
