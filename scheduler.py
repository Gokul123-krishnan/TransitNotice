import logging
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from config import Config
from services.scraping_service import ScrapingService
from services.notice_service import NoticeService

logger = logging.getLogger('transitnotice.scheduler')

scheduler = None

def run_scheduled_update():
    """Scheduled task executed periodically by the background scheduler."""
    logger.info("Starting scheduled Salem transit notices scrape & verification cycle...")
    try:
        report = ScrapingService.execute_scrape_cycle()
        logger.info(f"Scrape cycle completed: status={report.get('status')}, found={report.get('notices_found')}, added={report.get('notices_added')}, updated={report.get('notices_updated')}")
        NoticeService.sync_route_and_notice_statuses()
    except Exception as e:
        logger.error(f"Error during scheduled transit update cycle: {e}", exc_info=True)

def init_scheduler(app=None):
    """Initializes and starts the background update scheduler."""
    global scheduler
    if scheduler is not None and scheduler.running:
        return scheduler

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=run_scheduled_update,
        trigger="interval",
        minutes=Config.SCRAPER_INTERVAL_MINUTES,
        id="salem_transit_scrape_job",
        name="Salem City Bus Notice Scraper & Status Sync",
        replace_existing=True
    )

    scheduler.start()
    logger.info(f"Salem transit background scheduler started. Interval: every {Config.SCRAPER_INTERVAL_MINUTES} minutes.")

    # Graceful shutdown on app termination
    atexit.register(lambda: scheduler.shutdown(wait=False) if scheduler and scheduler.running else None)
    return scheduler

def get_scheduler_status():
    global scheduler
    if not scheduler:
        return {'running': False, 'next_run': None, 'interval_minutes': Config.SCRAPER_INTERVAL_MINUTES}
    
    job = scheduler.get_job("salem_transit_scrape_job")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
    return {
        'running': scheduler.running,
        'next_run': next_run,
        'interval_minutes': Config.SCRAPER_INTERVAL_MINUTES
    }
