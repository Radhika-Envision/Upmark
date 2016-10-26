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
    msg = MIMEText(template.format(message=errors), 'plain')
    msg['Subject'] = config['ERROR_SUBJECT']

    send(config, msg, config['ERROR_SEND_TO'])


def process_once(config):
    count = 0
    n_errors = 0
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
            if count == 0:
                log.info("Starting new job")

            calculator = Calculator.scoring(sub)
            calculator.mark_entire_survey_dirty(sub.survey)
            calculator.execute()
            if sub.error:
                n_errors += 1
            count += 1

            sub.modified = sub.survey.modified
            session.commit()

    log.info("Successfully recalculated scores for %d submissions.", count)
    log.info("Of those, %d contain user errors.", n_errors)
    return count, n_errors


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
        if '--test' in sys.argv:
            log.info("Sending test email")
            config = utils.get_config("recalculate.yaml")
            send_email(config, "Test")
            sys.exit(0)
        if not '--no-delay' in sys.argv:
            log.info("Sleeping for %ds", STARTUP_DELAY)
            time.sleep(STARTUP_DELAY)
        process_loop()
    except KeyboardInterrupt:
        log.info("Shutting down due to user request (e.g. Ctrl-C)")
