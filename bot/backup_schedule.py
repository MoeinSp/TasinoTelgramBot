_scheduler = None

def set_scheduler(scheduler):
    global _scheduler
    _scheduler = scheduler

def set_backup_interval(hours: int):
    if _scheduler is None:
        return False
    job = _scheduler.get_job("db_backup_3h")
    if job is None:
        return False
    job.reschedule(trigger="interval", hours=hours)
    return True
