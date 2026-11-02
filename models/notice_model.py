import json
import datetime
from database import parse_dt, format_dt, get_now_ist
from config import Config

class Notice:
    def __init__(self, **kwargs):
        self.notice_id = kwargs.get('notice_id')
        self.agency = kwargs.get('agency')
        self.agency_name = kwargs.get('agency_name')
        self.route_id = kwargs.get('route_id')
        self.area = kwargs.get('area')
        self.source_url = kwargs.get('source_url')
        self.notice_type = kwargs.get('notice_type')
        self.summary = kwargs.get('summary')
        self.description = kwargs.get('description', '')
        self.published_at = kwargs.get('published_at')
        self.valid_from = kwargs.get('valid_from')
        self.valid_to = kwargs.get('valid_to')
        self.status = kwargs.get('status', 'ACTIVE')
        self.observed_at = kwargs.get('observed_at')
        self.last_confirmed_at = kwargs.get('last_confirmed_at')
        self.content_hash = kwargs.get('content_hash')
        self.revision_id = kwargs.get('revision_id', 1)
        self.change_summary = kwargs.get('change_summary', '')
        self.alert_status = kwargs.get('alert_status', 'WARNING')
        self.alerted_at = kwargs.get('alerted_at')
        self.is_sample = kwargs.get('is_sample', 0)

    @classmethod
    def from_row(cls, row):
        if not row:
            return None
        d = dict(row)
        return cls(**d)

    @property
    def is_expired(self):
        v_to = parse_dt(self.valid_to)
        if not v_to:
            return False
        return v_to < get_now_ist()

    @property
    def is_stale(self):
        """A notice not confirmed for more than 48 hours is considered stale."""
        confirmed = parse_dt(self.last_confirmed_at)
        if not confirmed:
            return True
        diff = get_now_ist() - confirmed
        return diff.total_seconds() > (48 * 3600)

    @property
    def effective_status(self):
        """Validation Rule: An expired notice must never appear as currently active."""
        if self.is_expired:
            return 'EXPIRED'
        if self.status in ['CANCELLED', 'RESTORED', 'PARTIAL', 'DIVERTED', 'SUSPENDED']:
            return self.status
        v_from = parse_dt(self.valid_from)
        if v_from and v_from > get_now_ist():
            return 'UPCOMING'
        return 'ACTIVE'

    @property
    def status_badge_class(self):
        mapping = {
            'ACTIVE': 'badge-status-active',
            'UPCOMING': 'badge-status-upcoming',
            'EXPIRED': 'badge-status-expired',
            'CANCELLED': 'badge-status-cancelled',
            'RESTORED': 'badge-status-restored',
            'DIVERTED': 'badge-route-diverted',
            'SUSPENDED': 'badge-route-suspended',
            'PARTIAL': 'badge-route-partial'
        }
        return mapping.get(self.effective_status, 'badge-status-secondary')

    @property
    def alert_badge_class(self):
        mapping = {
            'CRITICAL': 'alert-pill-critical',
            'WARNING': 'alert-pill-warning',
            'INFO': 'alert-pill-info',
            'RESOLVED': 'alert-pill-resolved'
        }
        return mapping.get(self.alert_status, 'alert-pill-info')

    @property
    def formatted_published_at(self):
        dt = parse_dt(self.published_at)
        return dt.strftime('%d %b %Y, %I:%M %p IST') if dt else self.published_at

    @property
    def formatted_valid_from(self):
        dt = parse_dt(self.valid_from)
        return dt.strftime('%d %b %Y, %I:%M %p') if dt else self.valid_from

    @property
    def formatted_valid_to(self):
        dt = parse_dt(self.valid_to)
        return dt.strftime('%d %b %Y, %I:%M %p') if dt else self.valid_to

    @property
    def formatted_last_confirmed(self):
        dt = parse_dt(self.last_confirmed_at)
        return dt.strftime('%d %b %Y, %I:%M %p IST') if dt else self.last_confirmed_at

    @property
    def affected_routes_list(self):
        if not self.route_id:
            return []
        parts = [p.strip() for p in str(self.route_id).split(',') if p.strip()]
        return parts

    @property
    def affected_areas_list(self):
        if not self.area:
            return []
        parts = [p.strip() for p in str(self.area).split(',') if p.strip()]
        return parts

    def to_dict(self):
        return {
            'notice_id': self.notice_id,
            'agency': self.agency,
            'agency_name': self.agency_name,
            'route_id': self.route_id,
            'area': self.area,
            'source_url': self.source_url,
            'notice_type': self.notice_type,
            'summary': self.summary,
            'description': self.description,
            'published_at': self.published_at,
            'valid_from': self.valid_from,
            'valid_to': self.valid_to,
            'status': self.effective_status,
            'observed_at': self.observed_at,
            'last_confirmed_at': self.last_confirmed_at,
            'content_hash': self.content_hash,
            'revision_id': self.revision_id,
            'change_summary': self.change_summary,
            'alert_status': self.alert_status,
            'alerted_at': self.alerted_at,
            'is_sample': self.is_sample,
            'is_expired': self.is_expired,
            'is_stale': self.is_stale,
            'affected_routes': self.affected_routes_list,
            'affected_areas': self.affected_areas_list,
            'formatted_last_confirmed': self.formatted_last_confirmed
        }

class BusRoute:
    def __init__(self, **kwargs):
        self.route_id = kwargs.get('route_id')
        self.route_number = kwargs.get('route_number')
        self.origin = kwargs.get('origin')
        self.destination = kwargs.get('destination')
        self.key_stops = kwargs.get('key_stops')
        self.description = kwargs.get('description', '')
        self.operating_agency = kwargs.get('operating_agency')
        self.status = kwargs.get('status', 'NORMAL')
        self.is_manual_override = kwargs.get('is_manual_override', 0)
        self.last_updated = kwargs.get('last_updated')
        self.active_notices_count = kwargs.get('active_notices_count', 0)

    @classmethod
    def from_row(cls, row):
        if not row:
            return None
        return cls(**dict(row))

    @property
    def stops_list(self):
        if not self.key_stops:
            return []
        return [s.strip() for s in self.key_stops.split(',') if s.strip()]

    @property
    def status_class(self):
        mapping = {
            'NORMAL': 'badge-route-normal',
            'DIVERTED': 'badge-route-diverted',
            'SUSPENDED': 'badge-route-suspended',
            'PARTIAL': 'badge-route-partial'
        }
        return mapping.get(self.status, 'badge-route-normal')
