"""Background run of the bulk WebP conversion for the admin page.

There is no task queue here, so the run is a daemon thread in the web process. Its progress lives in the
`jobs` cache, which is file-based (config/settings.py), so every gunicorn worker sees the same job. A run
that stops reporting for STALE_AFTER seconds (process restarted) is treated as dead and can be started again.
"""
import threading
import time

from django.core.cache import caches
from django.db import close_old_connections

from .image_service import convert_stored_images

KEY = 'image-webp-job'
TTL = 6 * 60 * 60
STALE_AFTER = 10 * 60


def _cache():
    return caches['jobs']


def status():
    job = _cache().get(KEY)
    if job and job['state'] == 'running' and time.time() - job['updated'] > STALE_AFTER:
        job = {**job, 'state': 'failed', 'error': 'اجرا ناتمام ماند (سرور راه‌اندازی مجدد شده است).'}
    return job


def _save(job):
    job['updated'] = time.time()
    _cache().set(KEY, job, TTL)


def _run(options):
    job = {'state': 'running', 'done': 0, 'total': 0, 'reported': False, 'started': time.time()}
    _save(job)

    def progress(done, total):
        job.update(done=done, total=total)
        if done % 5 == 0 or done == total:
            _save(job)

    try:
        summary = convert_stored_images(progress=progress, **options)
        job.update(
            state='done', converted=summary.converted, skipped=summary.skipped, failed=summary.failed,
            saved=summary.bytes_saved, errors=summary.errors[:10],
        )
    except Exception as exc:
        job.update(state='failed', error=str(exc))
    finally:
        close_old_connections()
    _save(job)


def start(**options):
    """Start a run unless one is already going; returns whether it started."""
    current = status()
    if current and current['state'] == 'running':
        return False
    _save({'state': 'running', 'done': 0, 'total': 0, 'reported': False, 'started': time.time()})
    threading.Thread(target=_run, args=(options,), daemon=True, name='webp-convert').start()
    return True


def mark_reported(job):
    _cache().set(KEY, {**job, 'reported': True}, TTL)
