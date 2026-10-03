from celery import shared_task
from .services import expire_unconfirmed_entries


@shared_task
def expire_pending_partners():
    return expire_unconfirmed_entries()
