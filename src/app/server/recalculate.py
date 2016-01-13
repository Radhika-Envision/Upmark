import datetime
from email.mime.text import MIMEText
import logging
import os
from string import Template
import time

from sqlalchemy import or_

from mail import get_config, send
import model


logging.basicConfig(format='%(asctime)s %(message)s')
log = logging.getLogger('app.recalculate')
log.setLevel(logging.INFO)

interval = 300


def mail_content(errors):
    content = ''
    for err in errors:
        content += "Submission: %s\n" % str(err['submission_id']) 
        content += "Title: %s\n" % err['submission_title']
        content += "Message: %s\n\n" % err['error']
    return content


def send_email(config, errors):

    template = Template(config['MESSAGE_CONTENT'])
    msg = MIMEText(template.substitute(message=mail_content(errors)), 'text/plain')

    msg['Subject'] = config['MESSAGE_SUBJECT']
    msg['From'] = config['MESSAGE_SEND_FROM']
    msg['To'] = config['MESSAGE_SEND_TO']

    send(config, msg)


def process():
    config = get_config("recalculate.yaml")
    while True:
        count = 0
        errors = []
        while True:
            with model.session_scope() as session:
                sub = (session.query(model.Assessment)
                    .join(model.Hierarchy)
                    .filter(or_(model.Hierarchy.modified > model.Assessment.modified,
                        model.Assessment.modified == None))
                    .first())
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

        log.info("Job finished")
        log.info("Successfully recalculated scores for %d submissions.",
                 count)
        log.info("Fail to recalculate scores for %d submissions.",
                 len(errors))

        time.sleep(interval)


def connect_db():
    model.connect_db(os.environ.get('DATABASE_URL'))


if __name__ == "__main__":
    try:
        log.info("Starting service...:%s", datetime.datetime.utcnow())
        connect_db()
        time.sleep(interval)
        process()
    except KeyboardInterrupt:
        log.info("Shutting down due to user request (e.g. Ctrl-C)")
