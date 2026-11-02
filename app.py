import functools
import os
import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import check_password_hash

from config import Config
from database import init_db, seed_db, get_db, format_dt, parse_dt, get_now_ist
from models.notice_model import Notice, BusRoute
from services.notice_service import NoticeService
from services.notification_service import NotificationService
from services.scraping_service import ScrapingService
from scheduler import init_scheduler, get_scheduler_status

app = Flask(__name__)
app.config.from_object(Config)

# Ensure DB is initialized and seeded
with app.app_context():
    init_db()
    seed_db()

# Start background scraper scheduler
init_scheduler(app)

def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if not session.get('admin_logged_in'):
            flash("Administrator authentication required to access this portal.", "warning")
            return redirect(url_for('admin_login', next=request.url))
        return view(**kwargs)
    return wrapped_view

@app.context_processor
def inject_global_data():
    now_ist = get_now_ist()
    return {
        'salem_areas': Config.SALEM_KEY_AREAS,
        'current_time_ist': now_ist.strftime('%d %b %Y, %I:%M %p IST'),
        'unread_notifications_count': NotificationService.get_unread_count(),
        'app_city': Config.CITY_NAME,
        'app_state': Config.STATE_NAME
    }

# ==================== PUBLIC ROUTES ====================

@app.route('/')
def index():
    stats = NoticeService.get_dashboard_statistics()
    # Get active/recent notices for home feed
    recent_notices = NoticeService.get_notices({'status': 'ACTIVE'})[:5]
    all_routes = NoticeService.get_bus_routes()[:6]
    return render_template(
        'index.html',
        active_page='home',
        stats=stats,
        recent_notices=recent_notices,
        featured_routes=all_routes
    )

@app.route('/routes')
def routes():
    q = request.args.get('q', '').strip()
    area = request.args.get('area', '').strip()
    status = request.args.get('status', '').strip()
    
    bus_routes = NoticeService.get_bus_routes(
        search_term=q if q else None,
        area_filter=area if area else None,
        status_filter=status if status else None
    )
    bus_stops = NoticeService.get_bus_stops()
    
    return render_template(
        'routes.html',
        active_page='routes',
        routes=bus_routes,
        bus_stops=bus_stops,
        current_query=q,
        current_area=area,
        current_status=status
    )

@app.route('/notices')
def notices():
    filters = {
        'q': request.args.get('q', '').strip(),
        'route': request.args.get('route', '').strip(),
        'area': request.args.get('area', '').strip(),
        'notice_type': request.args.get('notice_type', '').strip(),
        'status': request.args.get('status', 'ALL').strip(),
        'origin': request.args.get('origin', '').strip(),
        'destination': request.args.get('destination', '').strip(),
        'date': request.args.get('date', '').strip()
    }
    
    all_notices = NoticeService.get_notices(filters)
    all_routes = NoticeService.get_bus_routes()
    
    return render_template(
        'notices.html',
        active_page='notices',
        notices=all_notices,
        filters=filters,
        routes=all_routes
    )

@app.route('/notices/<notice_id>')
def notice_details(notice_id):
    notice, history = NoticeService.get_notice_by_id(notice_id)
    if not notice:
        flash(f"Notice '{notice_id}' was not found.", "danger")
        return redirect(url_for('notices'))
    
    # Get affected route objects for display
    affected_routes_data = []
    if notice.affected_routes_list:
        for r_num in notice.affected_routes_list:
            matches = NoticeService.get_bus_routes(search_term=r_num)
            for m in matches:
                if m.route_id == r_num or m.route_number == f"Route {r_num}":
                    affected_routes_data.append(m)
                    break
    
    return render_template(
        'notice_details.html',
        active_page='notices',
        notice=notice,
        history=history,
        affected_routes=affected_routes_data
    )

@app.route('/about')
def about():
    agencies = NoticeService.get_agencies()
    scheduler_status = get_scheduler_status()
    return render_template(
        'about.html',
        active_page='about',
        agencies=agencies,
        scheduler_status=scheduler_status
    )

# ==================== ADMIN & AUTH ROUTES ====================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM admin_users WHERE username = ?", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['admin_logged_in'] = True
            session['admin_user'] = user['username']
            session['admin_name'] = user['full_name']
            session['admin_role'] = user['role']
            
            # Update last login
            now_str = format_dt(get_now_ist())
            cursor.execute("UPDATE admin_users SET last_login = ? WHERE user_id = ?", (now_str, user['user_id']))
            conn.commit()
            conn.close()

            flash(f"Welcome back, {user['full_name']}! Signed in successfully.", "success")
            next_url = request.args.get('next') or url_for('admin_dashboard')
            return redirect(next_url)
        else:
            conn.close()
            flash("Invalid administrator credentials. Please check username and password.", "danger")

    return render_template('admin_login.html', active_page='admin_login')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash("You have been signed out of the Administrator Portal.", "info")
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    stats = NoticeService.get_dashboard_statistics()
    all_notices = NoticeService.get_notices()
    routes = NoticeService.get_bus_routes()
    agencies = NoticeService.get_agencies()
    logs = ScrapingService.get_recent_logs(limit=15)
    scheduler_status = get_scheduler_status()

    return render_template(
        'admin_dashboard.html',
        active_page='admin_dashboard',
        stats=stats,
        notices=all_notices,
        routes=routes,
        agencies=agencies,
        scraper_logs=logs,
        scheduler_status=scheduler_status
    )

@app.route('/admin/notices/create', methods=['POST'])
@admin_required
def admin_create_notice():
    try:
        data = {
            'agency': request.form.get('agency', 'TNSTC-SLM'),
            'route_id': request.form.get('route_id', '').strip(),
            'area': request.form.get('area', '').strip(),
            'source_url': request.form.get('source_url', '').strip(),
            'notice_type': request.form.get('notice_type', 'Route Diversion'),
            'summary': request.form.get('summary', '').strip(),
            'description': request.form.get('description', '').strip(),
            'published_at': request.form.get('published_at') or format_dt(get_now_ist()),
            'valid_from': request.form.get('valid_from'),
            'valid_to': request.form.get('valid_to'),
            'alert_status': request.form.get('alert_status', 'WARNING'),
            'status': request.form.get('status', 'ACTIVE'),
            'is_sample': 1 if request.form.get('is_sample') else 0
        }

        # Validation: valid_to must be after valid_from
        if data['valid_from'] and data['valid_to']:
            if parse_dt(data['valid_to']) <= parse_dt(data['valid_from']):
                flash("Validation Error: Notice 'Valid To' date/time must be strictly after 'Valid From'.", "danger")
                return redirect(url_for('admin_dashboard'))

        notice_id = NoticeService.create_notice(data, modified_by=session.get('admin_name', 'Admin'))
        flash(f"Transit notice {notice_id} successfully created and broadcasted.", "success")
    except Exception as e:
        flash(f"Error creating notice: {str(e)}", "danger")

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/notices/edit/<notice_id>', methods=['POST'])
@admin_required
def admin_edit_notice(notice_id):
    try:
        data = {
            'agency': request.form.get('agency'),
            'route_id': request.form.get('route_id', '').strip(),
            'area': request.form.get('area', '').strip(),
            'source_url': request.form.get('source_url', '').strip(),
            'notice_type': request.form.get('notice_type'),
            'summary': request.form.get('summary', '').strip(),
            'description': request.form.get('description', '').strip(),
            'valid_from': request.form.get('valid_from'),
            'valid_to': request.form.get('valid_to'),
            'status': request.form.get('status'),
            'alert_status': request.form.get('alert_status')
        }

        success, msg = NoticeService.update_notice(notice_id, data, modified_by=session.get('admin_name', 'Admin'))
        if success:
            flash(f"Notice {notice_id} successfully updated: {msg}", "success")
        else:
            flash(f"Update failed: {msg}", "danger")
    except Exception as e:
        flash(f"Error updating notice: {str(e)}", "danger")

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/notices/delete/<notice_id>', methods=['POST'])
@admin_required
def admin_delete_notice(notice_id):
    try:
        NoticeService.delete_notice(notice_id)
        flash(f"Notice {notice_id} has been permanently deleted from records.", "info")
    except Exception as e:
        flash(f"Error deleting notice: {str(e)}", "danger")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/routes/manage', methods=['POST'])
@admin_required
def admin_manage_route():
    try:
        route_id = request.form.get('route_id', '').strip()
        route_number = request.form.get('route_number', '').strip()
        origin = request.form.get('origin', '').strip()
        destination = request.form.get('destination', '').strip()
        key_stops = request.form.get('key_stops', '').strip()
        description = request.form.get('description', '').strip()
        operating_agency = request.form.get('operating_agency', 'TNSTC-SLM').strip()
        status = request.form.get('status', 'NORMAL').strip().upper()

        if not route_id or not route_number or not origin or not destination:
            flash("Route ID, Number, Origin, and Destination are mandatory.", "danger")
            return redirect(url_for('admin_dashboard'))

        NoticeService.add_or_update_route(
            route_id=route_id,
            route_number=route_number,
            origin=origin,
            destination=destination,
            key_stops=key_stops,
            description=description,
            operating_agency=operating_agency,
            status=status
        )
        flash(f"Route '{route_number}' successfully saved with status {status}.", "success")
    except Exception as e:
        flash(f"Error managing route: {str(e)}", "danger")

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/routes/status/<route_id>', methods=['POST'])
@admin_required
def admin_change_route_status(route_id):
    try:
        new_status = request.form.get('status', 'NORMAL').strip()
        NoticeService.change_route_status(route_id, new_status)
        flash(f"Route {route_id} status updated to {new_status}.", "success")
    except Exception as e:
        flash(f"Error changing route status: {str(e)}", "danger")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/scraper/refresh', methods=['POST'])
@admin_required
def admin_trigger_scraper():
    """Manual trigger to refresh permitted public sources and detect updates."""
    try:
        report = ScrapingService.execute_scrape_cycle()
        msg = f"Scraper cycle executed: Found {report['notices_found']} notices, {report['notices_added']} added, {report['notices_updated']} updated in {report['duration_ms']}ms."
        if report['status'] == 'WARNING':
            flash(f"{msg} Note: {report.get('error_message')}", "warning")
        elif report['status'] == 'FAILED':
            flash(f"Scraper encountered an issue: {report.get('error_message')}", "danger")
        else:
            flash(msg, "success")
    except Exception as e:
        flash(f"Error running scraper cycle: {str(e)}", "danger")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/notification/broadcast-demo', methods=['POST'])
@admin_required
def admin_broadcast_demo():
    ntype = request.form.get('demo_type', 'RESTORED_SERVICE')
    NotificationService.broadcast_demo_notification(ntype)
    flash(f"Demonstration alert broadcasted: {ntype.replace('_', ' ').title()}", "info")
    return redirect(url_for('admin_dashboard'))

# ==================== REST APIs ====================

@app.route('/api/notifications', methods=['GET'])
def api_get_notifications():
    unread_only = request.args.get('unread') == '1'
    items = NotificationService.get_notifications(limit=15, unread_only=unread_only)
    unread_count = NotificationService.get_unread_count()
    return jsonify({
        'unread_count': unread_count,
        'notifications': items
    })

@app.route('/api/notifications/read/<int:nid>', methods=['POST'])
def api_mark_notification_read(nid):
    NotificationService.mark_as_read(nid)
    return jsonify({'success': True, 'unread_count': NotificationService.get_unread_count()})

@app.route('/api/notifications/read-all', methods=['POST'])
def api_mark_all_read():
    NotificationService.mark_all_as_read()
    return jsonify({'success': True, 'unread_count': 0})

@app.route('/api/stats', methods=['GET'])
def api_get_stats():
    stats = NoticeService.get_dashboard_statistics()
    return jsonify(stats)

if __name__ == '__main__':
    # Local development server
    app.run(host='127.0.0.1', port=5000, debug=True)
