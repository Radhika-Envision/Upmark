import datetime
from email.mime.text import MIMEText
import logging
import os
import sys
import time

from sqlalchemy import or_

from mail import send
import model
from score import Calculator
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

    template = config['ERROR_CONTENT']
    msg = MIMEText(template.format(message=errors), 'text/plain')
    msg['Subject'] = config['ERROR_SUBJECT']

    send(config, msg, config['ERROR_SEND_TO'])


def process_once(config):
    count = 0
    errors = []
    while True:
        with model.session_scope() as session:
            record = (session.query(model.Submission,
                                   model.Survey.modified)
                .join(model.Survey)
                .filter((model.Submission.modified < model.Survey.modified) |
                        ((model.Submission.modified == None) &
                         (model.Survey.modified != None)))
                .first())
            if record is None:
                break
            sub, htime = record
            log.info(
                "Processing %s, %s < %s", sub,
                sub and sub.modified, htime)
            if count == 0 and len(errors) == 0:
                log.info("Starting new job")

            try:
                calculator = Calculator.scoring(sub)
                calculator.mark_all_measures_dirty()
                calculator.execute()
                count += 1
            except ResponseTypeError as error:
                errors.append({"submission_id": sub.id,
                               "submission_title": sub.title,
                               "error": str(error)})
                sub = session.query(model.Submission).get(sub.id)

            sub.modified = sub.survey.modified
            session.commit()

    if len(errors) != 0:
        send_email(config, mail_content(errors))

    log.info("Successfully recalculated scores for %d submissions.",
             count)
    log.info("Failed to recalculate scores for %d submissions.",
             len(errors))


def process_loop():
    config = utils.get_config("recalculate.yaml")
    try:
        while True:
            process_once(config)
            log.info("Sleeping for %ds", config['JOB_INTERVAL_SECONDS'])
            time.sleep(config['JOB_INTERVAL_SECONDS'])
    except Exception as e:
        send_email(config,
             "FATAL ERROR. Daemon will need to be fixed.\n%s" %
             str(e))
        raise


def connect_db():
    model.connect_db(os.environ.get('DATABASE_URL'))


if __name__ == "__main__":
    try:
        log.info("Starting service")
        connect_db()
        if not '--no-delay' in sys.argv:
            log.info("Sleeping for %ds", STARTUP_DELAY)
            time.sleep(STARTUP_DELAY)
        process_loop()
    except KeyboardInterrupt:
        log.info("Shutting down due to user request (e.g. Ctrl-C)")
