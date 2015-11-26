import logging
import time
import model
import app


log = logging.getLogger('recalculate')
interval = 300
time.sleep(interval)


app.connect_db()


while True:
    with model.session_scope() as session:
        sub = (session.query(model.Assessment)
            .join(model.Hierarchy)
            .filter(model.Hierarchy.modified > model.Assessment.modified)
            .first())
        if sub is not None:
            log.info("sub: %s", sub)
            print("sub: %s", sub)
            sub.update_stats_descendants()
            sub.modified = sub.hierarchy.modified
            session.commit()

    log.info("Heart beat!!")
    print("Heart beat!!")
    time.sleep(interval)