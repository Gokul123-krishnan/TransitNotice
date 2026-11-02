import json
import sqlite3
import datetime
from database import get_db, format_dt, parse_dt, get_now_ist
from models.notice_model import Notice, BusRoute
from services.notification_service import NotificationService
from config import Config

class NoticeService:
    @staticmethod
    def sync_route_and_notice_statuses():
        """
        Enforces validation rules:
        1. An expired notice must never appear as currently active (valid_to < now -> EXPIRED).
        2. Recalculates bus_routes status dynamically based on current ACTIVE/PARTIAL/DIVERTED/SUSPENDED notices,
           while preserving manual administrator overrides (is_manual_override = 1).
        """
        conn = get_db()
        cursor = conn.cursor()
        now_str = format_dt(get_now_ist())

        # Expire overdue notices
        cursor.execute("""
            UPDATE notices
            SET status = 'EXPIRED'
            WHERE valid_to < ? AND status IN ('ACTIVE', 'PARTIAL', 'DIVERTED', 'SUSPENDED')
        """, (now_str,))

        # Re-evaluate all bus routes
        cursor.execute("SELECT * FROM bus_routes")
        routes = cursor.fetchall()

        for r in routes:
            r_id = r['route_id']
            is_manual = r['is_manual_override'] if 'is_manual_override' in r.keys() else 0

            # If the administrator manually set an override for this route, preserve it
            if is_manual:
                continue

            # Check active notices affecting this route
            cursor.execute("""
                SELECT notice_type, status FROM notices
                WHERE status IN ('ACTIVE', 'PARTIAL', 'DIVERTED', 'SUSPENDED') AND (
                    route_id = ? OR
                    route_id LIKE ? OR
                    route_id LIKE ? OR
                    route_id LIKE ?
                )
            """, (r_id, f"{r_id},%", f"%,{r_id}", f"%,{r_id},%"))
            active_notices = cursor.fetchall()

            new_status = 'NORMAL'
            for n in active_notices:
                ntype = (n['notice_type'] or '').strip().upper()
                nstatus = (n['status'] or '').strip().upper()
                if nstatus == 'SUSPENDED' or ntype in ['SUSPENDED', 'TEMPORARY CANCELLATION', 'TRIP CANCELLATION'] or 'SUSPEND' in ntype:
                    new_status = 'SUSPENDED'
                    break
                elif nstatus == 'DIVERTED' or ntype in ['DIVERTED', 'ROUTE DIVERSION', 'ROAD CLOSURE', 'DIVERSION'] or 'DIVERT' in ntype:
                    if new_status != 'SUSPENDED':
                        new_status = 'DIVERTED'
                elif nstatus == 'PARTIAL' or ntype in ['PARTIAL', 'PLANNED MAINTENANCE', 'SERVICE INTERRUPTION', 'PARTIAL SERVICE'] or 'PARTIAL' in ntype:
                    if new_status not in ['SUSPENDED', 'DIVERTED']:
                        new_status = 'PARTIAL'

            cursor.execute("""
                UPDATE bus_routes
                SET status = ?, last_updated = ?
                WHERE route_id = ?
            """, (new_status, now_str, r_id))

        conn.commit()
        conn.close()

    @staticmethod
    def get_dashboard_statistics():
        NoticeService.sync_route_and_notice_statuses()
        conn = get_db()
        cursor = conn.cursor()
        now_str = format_dt(get_now_ist())

        # Total notices
        cursor.execute("SELECT COUNT(*) FROM notices")
        total_notices = cursor.fetchone()[0]

        # Active service alerts
        cursor.execute("SELECT COUNT(*) FROM notices WHERE status IN ('ACTIVE', 'PARTIAL', 'DIVERTED', 'SUSPENDED') AND valid_to >= ?", (now_str,))
        active_alerts = cursor.fetchone()[0]

        # Upcoming diversions
        cursor.execute("""
            SELECT COUNT(*) FROM notices
            WHERE status = 'UPCOMING' OR (valid_from > ? AND status != 'CANCELLED')
        """, (now_str,))
        upcoming_diversions = cursor.fetchone()[0]

        # Cancelled or expired notices
        cursor.execute("SELECT COUNT(*) FROM notices WHERE status IN ('EXPIRED', 'CANCELLED')")
        cancelled_or_expired = cursor.fetchone()[0]

        # Total Salem Routes
        cursor.execute("SELECT COUNT(*) FROM bus_routes")
        total_routes = cursor.fetchone()[0]

        # Diverted Routes
        cursor.execute("SELECT COUNT(*) FROM bus_routes WHERE status != 'NORMAL'")
        disrupted_routes = cursor.fetchone()[0]

        # Last verified time from latest scraper run or notice confirmation
        cursor.execute("SELECT checked_at FROM scraper_logs ORDER BY checked_at DESC LIMIT 1")
        last_log = cursor.fetchone()
        
        cursor.execute("SELECT last_confirmed_at FROM notices ORDER BY last_confirmed_at DESC LIMIT 1")
        last_notice = cursor.fetchone()

        last_verification = None
        if last_log and last_log['checked_at']:
            last_verification = last_log['checked_at']
        elif last_notice and last_notice['last_confirmed_at']:
            last_verification = last_notice['last_confirmed_at']
        else:
            last_verification = now_str

        # Format last verification nicely
        dt_v = parse_dt(last_verification)
        formatted_last_verification = dt_v.strftime('%d %b %Y, %I:%M %p IST') if dt_v else last_verification

        # Notice type breakdown for dashboard visualization
        cursor.execute("""
            SELECT notice_type, COUNT(*) as count
            FROM notices
            GROUP BY notice_type
        """)
        type_breakdown = [dict(r) for r in cursor.fetchall()]

        # Area breakdown
        cursor.execute("""
            SELECT area, COUNT(*) as count
            FROM notices
            GROUP BY area
            ORDER BY count DESC LIMIT 6
        """)
        area_breakdown = [dict(r) for r in cursor.fetchall()]

        conn.close()

        return {
            'total_notices': total_notices,
            'active_alerts': active_alerts,
            'upcoming_diversions': upcoming_diversions,
            'cancelled_or_expired': cancelled_or_expired,
            'total_routes': total_routes,
            'disrupted_routes': disrupted_routes,
            'last_verified_at': formatted_last_verification,
            'raw_last_verified_at': last_verification,
            'type_breakdown': type_breakdown,
            'area_breakdown': area_breakdown
        }

    @staticmethod
    def get_notices(filters=None):
        NoticeService.sync_route_and_notice_statuses()
        conn = get_db()
        cursor = conn.cursor()

        query = """
            SELECT n.*, a.name as agency_name, a.portal_url as agency_url
            FROM notices n
            LEFT JOIN agencies a ON n.agency = a.agency_id
            WHERE 1=1
        """
        params = []
        filters = filters or {}

        # Search query (matches summary, description, area, route_id)
        if filters.get('q'):
            q_term = f"%{filters['q'].strip()}%"
            query += " AND (n.summary LIKE ? OR n.description LIKE ? OR n.area LIKE ? OR n.route_id LIKE ?)"
            params.extend([q_term, q_term, q_term, q_term])

        # Filter by Route
        if filters.get('route'):
            r_str = filters['route'].strip()
            query += " AND (n.route_id = ? OR n.route_id LIKE ? OR n.route_id LIKE ? OR n.route_id LIKE ?)"
            params.extend([r_str, f"{r_str},%", f"%,{r_str}", f"%,{r_str},%"])

        # Filter by Salem Area
        if filters.get('area'):
            a_term = f"%{filters['area'].strip()}%"
            query += " AND n.area LIKE ?"
            params.append(a_term)

        # Filter by Announcement Type
        if filters.get('notice_type'):
            nt = filters['notice_type'].strip()
            if nt.upper() in ['DIVERTED', 'SUSPENDED', 'PARTIAL']:
                query += " AND (n.notice_type = ? OR n.notice_type LIKE ? OR n.status = ?)"
                params.extend([nt, f"%{nt}%", nt.upper()])
            else:
                query += " AND n.notice_type = ?"
                params.append(nt)

        # Filter by Status
        if filters.get('status'):
            st = filters['status'].strip().upper()
            if st != 'ALL':
                if st in ['ACTIVE', 'PARTIAL', 'DIVERTED', 'SUSPENDED']:
                    query += " AND (n.status = ? OR n.notice_type = ? OR n.notice_type LIKE ?)"
                    params.extend([st, st, f"%{st}%"])
                else:
                    query += " AND n.status = ?"
                    params.append(st)

        # Filter by Origin / Starting Point
        if filters.get('origin'):
            orig_term = f"%{filters['origin'].strip()}%"
            query += """ AND EXISTS (
                SELECT 1 FROM bus_routes br
                WHERE br.origin LIKE ? AND (
                    n.route_id = br.route_id OR
                    n.route_id LIKE br.route_id || ',%' OR
                    n.route_id LIKE '%,' || br.route_id OR
                    n.route_id LIKE '%,' || br.route_id || ',%'
                )
            )"""
            params.append(orig_term)

        # Filter by Destination
        if filters.get('destination'):
            dest_term = f"%{filters['destination'].strip()}%"
            query += """ AND EXISTS (
                SELECT 1 FROM bus_routes br
                WHERE br.destination LIKE ? AND (
                    n.route_id = br.route_id OR
                    n.route_id LIKE br.route_id || ',%' OR
                    n.route_id LIKE '%,' || br.route_id OR
                    n.route_id LIKE '%,' || br.route_id || ',%'
                )
            )"""
            params.append(dest_term)

        # Filter by Active on Date (valid_from <= date <= valid_to)
        if filters.get('date'):
            date_str = filters['date'].strip()
            # Ensure day comparison
            query += " AND date(n.valid_from) <= date(?) AND date(n.valid_to) >= date(?)"
            params.extend([date_str, date_str])

        query += " ORDER BY CASE n.status WHEN 'ACTIVE' THEN 1 WHEN 'UPCOMING' THEN 2 WHEN 'RESTORED' THEN 3 ELSE 4 END, n.published_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        notices = [Notice.from_row(r) for r in rows]
        conn.close()
        return notices

    @staticmethod
    def get_notice_by_id(notice_id):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT n.*, a.name as agency_name, a.authority_type as agency_type,
                   a.portal_url as agency_url, a.contact_info as agency_contact
            FROM notices n
            LEFT JOIN agencies a ON n.agency = a.agency_id
            WHERE n.notice_id = ?
        """, (notice_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None, []

        notice = Notice.from_row(row)

        # Fetch revision history
        cursor.execute("""
            SELECT * FROM notice_history
            WHERE notice_id = ?
            ORDER BY revision_id DESC, modified_at DESC
        """, (notice_id,))
        hist_rows = cursor.fetchall()
        history = [dict(h) for h in hist_rows]

        conn.close()
        return notice, history

    @staticmethod
    def get_bus_routes(search_term=None, area_filter=None, status_filter=None):
        NoticeService.sync_route_and_notice_statuses()
        conn = get_db()
        cursor = conn.cursor()

        query = "SELECT * FROM bus_routes WHERE 1=1"
        params = []

        if search_term:
            s = f"%{search_term.strip()}%"
            query += " AND (route_number LIKE ? OR origin LIKE ? OR destination LIKE ? OR key_stops LIKE ?)"
            params.extend([s, s, s, s])

        if area_filter:
            af = f"%{area_filter.strip()}%"
            query += " AND (key_stops LIKE ? OR origin LIKE ? OR destination LIKE ?)"
            params.extend([af, af, af])

        if status_filter and status_filter != 'ALL':
            query += " AND status = ?"
            params.append(status_filter.strip().upper())

        query += " ORDER BY CAST(route_id AS INTEGER) ASC, route_number ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Count active notices per route
        routes = []
        for r in rows:
            r_id = r['route_id']
            cursor.execute("""
                SELECT COUNT(*) FROM notices
                WHERE status IN ('ACTIVE', 'PARTIAL', 'DIVERTED', 'SUSPENDED') AND (
                    route_id = ? OR route_id LIKE ? OR route_id LIKE ? OR route_id LIKE ?
                )
            """, (r_id, f"{r_id},%", f"%,{r_id}", f"%,{r_id},%"))
            cnt = cursor.fetchone()[0]
            route_dict = dict(r)
            route_dict['active_notices_count'] = cnt
            routes.append(BusRoute.from_row(route_dict))

        conn.close()
        return routes

    @staticmethod
    def get_bus_stops():
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bus_stops ORDER BY area_name ASC, stop_name ASC")
        stops = [dict(s) for s in cursor.fetchall()]
        conn.close()
        return stops

    @staticmethod
    def get_agencies():
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM agencies ORDER BY name ASC")
        agencies = [dict(a) for a in cursor.fetchall()]
        conn.close()
        return agencies

    @staticmethod
    def create_notice(data, modified_by='Transport Admin'):
        conn = get_db()
        cursor = conn.cursor()
        now_str = format_dt(get_now_ist())

        # Generate unique notice ID if not provided
        notice_id = data.get('notice_id')
        if not notice_id:
            cursor.execute("SELECT COUNT(*) FROM notices")
            next_idx = cursor.fetchone()[0] + 1
            notice_id = f"SLM-TR-{get_now_ist().year}-{next_idx:04d}"

        # Calculate initial status based on valid_from
        valid_from = data.get('valid_from')
        valid_to = data.get('valid_to')
        status = data.get('status', 'ACTIVE')
        if valid_to and parse_dt(valid_to) and parse_dt(valid_to) < get_now_ist():
            status = 'EXPIRED'
        elif valid_from and parse_dt(valid_from) and parse_dt(valid_from) > get_now_ist() and status not in ['PARTIAL', 'DIVERTED', 'SUSPENDED']:
            status = 'UPCOMING'

        cursor.execute("""
            INSERT INTO notices (
                notice_id, agency, route_id, area, source_url, notice_type,
                summary, description, published_at, valid_from, valid_to,
                status, observed_at, last_confirmed_at, content_hash,
                revision_id, change_summary, alert_status, alerted_at, is_sample
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            notice_id,
            data.get('agency', 'TNSTC-SLM'),
            data.get('route_id', ''),
            data.get('area', 'Salem Central'),
            data.get('source_url', ''),
            data.get('notice_type', 'Route Diversion'),
            data.get('summary', ''),
            data.get('description', ''),
            data.get('published_at', now_str),
            valid_from,
            valid_to,
            status,
            now_str,
            now_str,
            data.get('content_hash', ''),
            1,
            'Initial announcement created.',
            data.get('alert_status', 'WARNING'),
            now_str,
            data.get('is_sample', 0)
        ))

        # Record in history
        cursor.execute("""
            INSERT INTO notice_history (
                notice_id, revision_id, change_type, old_data, new_data,
                change_notes, modified_by, modified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            notice_id, 1, 'CREATED', None,
            json.dumps({'summary': data.get('summary'), 'status': status, 'valid_to': valid_to}),
            'Notice officially created in system.',
            modified_by,
            now_str
        ))

        conn.commit()
        conn.close()

        # Trigger notification
        NotificationService.create_notification(
            notice_id=notice_id,
            title=f"New Notice: {data.get('notice_type')} ({data.get('area')})",
            message=data.get('summary', '')[:120],
            notification_type='NEW_NOTICE',
            severity=data.get('alert_status', 'WARNING')
        )

        NoticeService.sync_route_and_notice_statuses()
        return notice_id

    @staticmethod
    def update_notice(notice_id, data, modified_by='Transport Admin'):
        """Updates an existing notice, recording changes in notice_history and bumping revision."""
        conn = get_db()
        cursor = conn.cursor()
        now_str = format_dt(get_now_ist())

        cursor.execute("SELECT * FROM notices WHERE notice_id = ?", (notice_id,))
        current = cursor.fetchone()
        if not current:
            conn.close()
            return False, "Notice not found"

        current_dict = dict(current)
        new_rev = current_dict['revision_id'] + 1

        # Detect what changed
        changes = []
        change_type = 'MODIFIED'
        if data.get('valid_to') and data['valid_to'] != current_dict['valid_to']:
            changes.append(f"Validity extended from {current_dict['valid_to']} to {data['valid_to']}")
            change_type = 'EXTENDED'
        if data.get('status') and data['status'] != current_dict['status']:
            changes.append(f"Status changed from {current_dict['status']} to {data['status']}")
            if data['status'] == 'RESTORED':
                change_type = 'RESTORED'
            elif data['status'] == 'CANCELLED':
                change_type = 'CANCELLED'
        if data.get('summary') and data['summary'] != current_dict['summary']:
            changes.append("Summary details updated")

        change_notes = "; ".join(changes) if changes else "General details updated."

        # Compute status
        status = data.get('status', current_dict['status'])
        valid_to = data.get('valid_to', current_dict['valid_to'])
        if parse_dt(valid_to) < get_now_ist() and status not in ['CANCELLED', 'RESTORED']:
            status = 'EXPIRED'

        cursor.execute("""
            UPDATE notices
            SET agency = ?, route_id = ?, area = ?, source_url = ?, notice_type = ?,
                summary = ?, description = ?, valid_from = ?, valid_to = ?,
                status = ?, last_confirmed_at = ?, revision_id = ?,
                change_summary = ?, alert_status = ?
            WHERE notice_id = ?
        """, (
            data.get('agency', current_dict['agency']),
            data.get('route_id', current_dict['route_id']),
            data.get('area', current_dict['area']),
            data.get('source_url', current_dict['source_url']),
            data.get('notice_type', current_dict['notice_type']),
            data.get('summary', current_dict['summary']),
            data.get('description', current_dict['description']),
            data.get('valid_from', current_dict['valid_from']),
            valid_to,
            status,
            now_str,
            new_rev,
            change_notes,
            data.get('alert_status', current_dict['alert_status']),
            notice_id
        ))

        # Record in history
        cursor.execute("""
            INSERT INTO notice_history (
                notice_id, revision_id, change_type, old_data, new_data,
                change_notes, modified_by, modified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            notice_id, new_rev, change_type,
            json.dumps({'summary': current_dict['summary'], 'status': current_dict['status'], 'valid_to': current_dict['valid_to']}),
            json.dumps({'summary': data.get('summary'), 'status': status, 'valid_to': valid_to}),
            change_notes,
            modified_by,
            now_str
        ))

        conn.commit()
        conn.close()

        # Notification for extension or modification
        notif_type = 'MODIFIED_ROUTE'
        sev = data.get('alert_status', 'INFO')
        if change_type == 'EXTENDED':
            notif_type = 'EXTENDED_INTERRUPTION'
            sev = 'WARNING'
        elif change_type == 'RESTORED':
            notif_type = 'RESTORED_SERVICE'
            sev = 'RESOLVED'
        elif change_type == 'CANCELLED':
            notif_type = 'CANCELLED_NOTICE'
            sev = 'CRITICAL'

        NotificationService.create_notification(
            notice_id=notice_id,
            title=f"Notice Updated ({notice_id}): {change_type.replace('_', ' ').title()}",
            message=change_notes,
            notification_type=notif_type,
            severity=sev
        )

        NoticeService.sync_route_and_notice_statuses()
        return True, "Notice successfully updated"

    @staticmethod
    def delete_notice(notice_id):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM notices WHERE notice_id = ?", (notice_id,))
        cursor.execute("DELETE FROM notice_history WHERE notice_id = ?", (notice_id,))
        cursor.execute("DELETE FROM notifications WHERE notice_id = ?", (notice_id,))
        conn.commit()
        conn.close()
        NoticeService.sync_route_and_notice_statuses()
        return True

    @staticmethod
    def change_route_status(route_id, new_status):
        conn = get_db()
        cursor = conn.cursor()
        now_str = format_dt(get_now_ist())
        new_status = (new_status or 'NORMAL').strip().upper()

        if new_status == 'AUTO':
            # Reset manual override and dynamically sync from notices
            cursor.execute("""
                UPDATE bus_routes
                SET is_manual_override = 0, last_updated = ?
                WHERE route_id = ?
            """, (now_str, route_id))
            conn.commit()
            conn.close()
            NoticeService.sync_route_and_notice_statuses()
            return True

        # Administrator explicitly set manual override
        cursor.execute("""
            UPDATE bus_routes
            SET status = ?, is_manual_override = 1, last_updated = ?
            WHERE route_id = ?
        """, (new_status, now_str, route_id))
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def add_or_update_route(route_id, route_number, origin, destination, key_stops, description, operating_agency, status='NORMAL'):
        conn = get_db()
        cursor = conn.cursor()
        now_str = format_dt(get_now_ist())
        status = (status or 'NORMAL').strip().upper()
        is_manual = 1 if status in ['PARTIAL', 'DIVERTED', 'SUSPENDED'] else 0

        cursor.execute("SELECT route_id FROM bus_routes WHERE route_id = ?", (route_id,))
        exists = cursor.fetchone()
        if exists:
            cursor.execute("""
                UPDATE bus_routes
                SET route_number = ?, origin = ?, destination = ?, key_stops = ?,
                    description = ?, operating_agency = ?, status = ?, is_manual_override = ?, last_updated = ?
                WHERE route_id = ?
            """, (route_number, origin, destination, key_stops, description, operating_agency, status, is_manual, now_str, route_id))
        else:
            cursor.execute("""
                INSERT INTO bus_routes (
                    route_id, route_number, origin, destination, key_stops,
                    description, operating_agency, status, is_manual_override, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (route_id, route_number, origin, destination, key_stops, description, operating_agency, status, is_manual, now_str))
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def delete_route(route_id):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bus_routes WHERE route_id = ?", (route_id,))
        conn.commit()
        conn.close()
        return True
