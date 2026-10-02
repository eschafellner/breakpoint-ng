from celery import shared_task
from .services import end_expired_memberships

@shared_task
def task_end_expired_memberships():
    """Daily Celery Beat task to terminate memberships reaching end_date."""
    ended = end_expired_memberships()
    return f"Ended {ended} expired memberships."
