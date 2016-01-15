import datetime
from email.mime.text import MIMEText
import logging
import os
import time

from sqlalchemy import or_

from mail import send
import model
import utils


logging.basicConfig(format='%(asctime)s %(message)s')
log = logging.getLogger('app.recalculate')
log.setLevel(logging.INFO)

STARTUP_DELAY = 60


def mail_content(errors):
    content = ''
    for err in errors:
        content += "Submission: %s\n" % str(err['submission_id']) 
        content += "Title: %s\n" % err['submission_title']
        content += "Message: %s\n\n" % err['error']
    return content


def send_email(config, errors):

    template = config['MESSAGE_CONTENT']
    msg = MIMEText(template.format(message=mail_content(errors)), 'text/plain')

    msg['Subject'] = config['MESSAGE_SUBJECT']
    msg['From'] = config['MESSAGE_SEND_FROM']
    msg['To'] = config['MESSAGE_SEND_TO']

    send(config, msg)


def process_once(config):
    count = 0
    errors = []
    while True:
        with model.session_scope() as session:
            sub = (session.query(model.Assessment)
                .join(model.Hierarchy)
                .filter(or_(model.Hierarchy.modified > model.Assessment.modified,
                    model.Assessment.modified == None))
                .first())
            log.info("Processing %s", sub)
            if sub is None:
                break
            if count == 0 and len(errors) == 0:
                log.info("Starting new job")

            try:
                sub.update_stats_descendants()
                count += 1
            except model.ModelError as error:
                errors.append({"submission_id": sub.id,
                               "submission_title": sub.title,
                               "error": str(error)})
                sub = session.query(model.Assessment).get(sub.id)

            sub.modified = sub.hierarchy.modified
            session.commit()

    if len(errors) != 0:
        send_email(config, errors)

    log.info("Successfully recalculated scores for %d submissions.",
             count)
    log.info("Failed to recalculate scores for %d submissions.",
             len(errors))


def process_loop():
    config = utils.get_config("recalculate.yaml")
    while True:
        process_once(config)
        log.info("Sleeping for %ds", config['JOB_INTERVAL_SECONDS'])
        time.sleep(config['JOB_INTERVAL_SECONDS'])


def connect_db():
    model.connect_db(os.environ.get('DATABASE_URL'))


if __name__ == "__main__":
    try:
        log.info("Starting service")
        connect_db()
        log.info("Sleeping for %ds", STARTUP_DELAY)
        time.sleep(STARTUP_DELAY)
        process_loop()
    except KeyboardInterrupt:
        log.info("Shutting down due to user request (e.g. Ctrl-C)")
