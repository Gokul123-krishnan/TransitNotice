import sqlite3
import datetime
from database import get_db, format_dt, get_now_ist
from config import Config

class NotificationService:
    @staticmethod
    def create_notification(notice_id, title, message, notification_type, severity='INFO'):
        """Creates an in-app notification if a duplicate does not already exist."""
        conn = get_db()
        cursor = conn.cursor()
        now_str = format_dt(get_now_ist())

        # Duplicate prevention: check if same notice_id, notification_type exists within last 2 hours
        cursor.execute("""
            SELECT notification_id FROM notifications
            WHERE notice_id = ? AND notification_type = ?
            ORDER BY created_at DESC LIMIT 1
        """, (notice_id, notification_type))
        existing = cursor.fetchone()

        if existing:
            conn.close()
            return False, "Duplicate notification prevented"

        cursor.execute("""
            INSERT INTO notifications (notice_id, title, message, notification_type, severity, is_read, created_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (notice_id, title, message, notification_type, severity, now_str))

        conn.commit()
        conn.close()
        return True, "Notification created"

    @staticmethod
    def get_unread_count():
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM notifications WHERE is_read = 0")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    @staticmethod
    def get_notifications(limit=20, unread_only=False):
        conn = get_db()
        cursor = conn.cursor()
        query = "SELECT * FROM notifications"
        params = []
        if unread_only:
            query += " WHERE is_read = 0"
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        notifications = [dict(r) for r in rows]
        conn.close()
        return notifications

    @staticmethod
    def mark_as_read(notification_id):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE notifications SET is_read = 1 WHERE notification_id = ?", (notification_id,))
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def mark_all_as_read():
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
        conn.commit()
        conn.close()
        return True

    @staticmethod
    def broadcast_demo_notification(notice_type="RESTORED_SERVICE"):
        """Safe demonstration broadcast for testing real-time notifications in UI."""
        now_str = datetime.datetime.now(Config.TIMEZONE).strftime('%I:%M %p')
        types_map = {
            "NEW_NOTICE": ("New Transit Notice Issued", "TNSTC issued a fresh traffic advisory for Hasthampatti roundabout.", "WARNING"),
            "MODIFIED_ROUTE": ("Bus Route Diversion Updated", "Salem City Traffic Police updated alternative lanes near Meyyanur.", "INFO"),
            "EXTENDED_INTERRUPTION": ("Advisory Extended", "Culvert concrete curing at Five Roads extended for 24 hours.", "WARNING"),
            "CANCELLED_NOTICE": ("Temporary Cancellation Advisory", "Mid-day trips on Ammapet sector temporarily paused.", "CRITICAL"),
            "RESTORED_SERVICE": ("Service Restored", "Regular bus operations resumed on Salem Steel Plant corridor.", "RESOLVED")
        }
        title, msg, sev = types_map.get(notice_type, ("Transit Advisory Notice", "Transit update for Salem city commuters.", "INFO"))
        return NotificationService.create_notification(
            notice_id="DEMO-ALERT-" + datetime.datetime.now(Config.TIMEZONE).strftime('%M%S'),
            title=f"Demo: {title} ({now_str})",
            message=msg,
            notification_type=notice_type,
            severity=sev
        )
