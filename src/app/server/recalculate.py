import logging
import time
import model
import datetime

from app import connect_db

log = logging.getLogger('app.recalculate')
log.setLevel(logging.INFO)

interval = 300

def process():
    while True:
        while True:
            with model.session_scope() as session:
                sub = (session.query(model.Assessment)
                    .join(model.Hierarchy)
                    .filter(model.Hierarchy.modified > model.Assessment.modified)
                    .first())
                if sub is not None:
                    sub.update_stats_descendants()
                    sub.modified = sub.hierarchy.modified
                    session.commit()

            log.info("Job finished: %s", datetime.datetime.utcnow())
            time.sleep(interval)

if __name__ == "__main__":
    try:
        log.info("Starting service...:%s", datetime.datetime.utcnow())
        connect_db()
        time.sleep(interval)
        process()
    except KeyboardInterrupt:
        log.info("Shutting down due to user request (e.g. Ctrl-C)")
