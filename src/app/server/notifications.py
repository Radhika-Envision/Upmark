import logging
import time
import model
import datetime

from mail import send, get_config
from string import Template
from email.mime.text import MIMEText
from app import connect_db

log = logging.getLogger('app.notifications')
log.setLevel(logging.INFO)

interval = 10 # seconds

def mail_content(user):
    return user.email

def send_email(config, user):

    template = Template(config['MESSAGE_CONTENT'])
    msg = MIMEText(template.substitute(message=mail_content(user)), 'text/plain')

    msg['Subject'] = config['MESSAGE_SUBJECT']
    msg['From'] = config['MESSAGE_SEND_FROM']
    msg['To'] = user.email

    send(config, msg)

def process():
    config = get_config("notification.yaml")
    while True:
        with model.session_scope() as session:
            user_list = session.query(model.AppUser)\
                .filter(model.AppUser.enabled)\
                .all()
            if user_list is None:
                break
            for user in user_list:
                now = datetime.datetime.utcnow()
                if user.email_time == None or user.email_interval == None:
                    send_email(config, user)
                    user.email_time = now
                elif user.email_time + datetime.timedelta(seconds=user.email_interval) < now: 
                    send_email(config, user)
                    user.email_time = now
            session.commit()

            log.info("Job finished. Email sent for notification")
            time.sleep(interval)

if __name__ == "__main__":
    try:
        log.info("Starting notification service...:%s", datetime.datetime.utcnow())
        connect_db()
        time.sleep(interval)
        process()
    except KeyboardInterrupt:
        log.info("Shutting down due to user request (e.g. Ctrl-C)")