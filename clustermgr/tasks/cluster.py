from clustermgr.extensions import celery


@celery.task(bind=True)
def add_these(a, b):
    return a+b
