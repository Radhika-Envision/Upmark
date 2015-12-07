import datetime
from email.mime.text import MIMEText
import logging
import os
from string import Template
import time

import model
import activity
from mail import send, get_config

logging.basicConfig(format='%(asctime)s %(message)s')
log = logging.getLogger('notifications')
log.setLevel(logging.INFO)

interval = 60 * 60 # seconds


def mail_content(activities):
    content = ''
    for act in activities:
        if act.verbs != 'broadcast':
            content += act.message + ' '
            content += act.subject.name + ' '
            content += 'this ' + act.ob_type + ' - '
            content += str(act.created) + '\n'
        else:
            content += act.message + '\n'
    return content


def send_email(config, user, activities):

    template = Template(config['MESSAGE_CONTENT'])
    msg = MIMEText(template.substitute(message=mail_content(activities)), 'text/plain')

    msg['Subject'] = config['MESSAGE_SUBJECT']
    msg['From'] = config['MESSAGE_SEND_FROM']
    msg['To'] = user.email

    send(config, msg)


def get_activities(session, user):

    now = datetime.datetime.utcnow()
    activities = activity.Activities(session)
    from_date = user.email_time
    if from_date == None:
        from_date = now + datetime.timedelta(days=-7)
    activities_timeline = activities.timeline_query(user.id,
                                                    from_date,
                                                    now,
                                                    {'at_top'}).all()

    return activities_timeline


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
                if (user.email_time == None or user.email_interval == None) or (
                    user.email_time + datetime.timedelta(seconds=user.email_interval) < now):
                    activities = get_activities(session, user)
                    if len(activities) != 0:
                        send_email(config, user, activities)
                        user.email_time = now
            session.commit()

            log.info("Job finished. Email sent for notification")
            time.sleep(interval)


def connect_db():
    model.connect_db(os.environ.get('DATABASE_URL'))


if __name__ == "__main__":
    try:
        log.info("Starting notification service...:%s", datetime.datetime.utcnow())
        connect_db()
        time.sleep(interval)
        process()
    except KeyboardInterrupt:
        log.info("Shutting down due to user request (e.g. Ctrl-C)")
