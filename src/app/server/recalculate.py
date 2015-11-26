import logging
import time
import model
import datetime

from app import connect_db

connect_db()

log = logging.getLogger('recalculate')
log.setLevel(logging.INFO)

interval = 300
log.info("Starting service...:%s", datetime.datetime.utcnow())

time.sleep(interval)
while True:
    with model.session_scope() as session:
        sub = (session.query(model.Assessment)
            .join(model.Hierarchy)
            .filter(model.Hierarchy.modified > model.Assessment.modified)
            .first())
        if sub is not None:
            log.info("sub: %s", sub)
            sub.update_stats_descendants()
            sub.modified = sub.hierarchy.modified
            session.commit()

    log.info("Job finished: %s", datetime.datetime.utcnow())
    time.sleep(interval)