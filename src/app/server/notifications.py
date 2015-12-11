import datetime
from email.mime.text import MIMEText
import logging
from mail import send, get_config
import os
from string import Template
import time

from sqlalchemy import extract, func

import activity
import model


logging.basicConfig(format='%(asctime)s %(message)s')
log = logging.getLogger('notifications')
log.setLevel(logging.INFO)


def mail_content(config, activities):
    content = ''
    template_bc = Template(config['MESSAGE_BROADCAST'])
    template_std = Template(config['MESSAGE_STANDARD'])
    for act in activities:
        if 'broadcast' in act.verbs:
            template = template_bc
        else:
            template = template_std

        content += template.substitute(
            user_name=act.subject.name, message=act.message,
            ob_type=ob_type(act), verbs=verbs(act),
            date=str(act.created))
        content += "\n"

    return content


def ob_type(action):
    if action.ob_type == 'qnode':
        return 'survey category'
    elif action.ob_type == 'rnode':
        return 'submission category'
    else:
        return action.ob_type


def verbs(action):
    expr = ""
    for i, verb in enumerate(action.verbs):
        if i > 0 and i == len(action.verbs) - 1
            expr += " and "
        elif i > 0
            expr += ", "

        if verb == 'create':
            verb = 'created'
        elif verb == 'update':
            verb = 'modified'
        elif verb == 'state':
            verb = 'changed the state of'
        elif verb == 'delete':
            verb = 'deleted'
        elif verb == 'relation':
            verb = '(re)linked'
        elif verb == 'reorder_children':
            verb = 'reordered the children of'

        expr += verb;

    return expr;


def send_email(config, user, activities, messages):
    template = Template(config['MESSAGE_CONTENT'])
    content = mail_content(config, activities)
    message_str = "\n".join(messages)
    msg = MIMEText(
        template.substitute(
            activities=content, messages=message_str, user_id=user.id),
        'text/plain')

    msg['Subject'] = config['MESSAGE_SUBJECT']
    msg['From'] = config['MESSAGE_SEND_FROM']
    msg['To'] = user.email

    send(config, msg)


def get_activities(session, user, until_date, messages):
    activities = activity.Activities(session)
    from_date = user.email_time
    earliest_from_date = until_date - datetime.timedelta(days=15)
    if from_date is None or from_date < earliest_from_date:
        messages.append(
            "Requested start date was too early (%s).\n"
            "Showing events from %s instead." % (
                from_date, earliest_from_date))
        from_date = earliest_from_date
    activity_query = activities.timeline_query(
        user.id, from_date, until_date, {'at_top'})

    activity_query = activity_query.limit(MAX_ACTIVITIES)
    activities = list(activity_query.all())
    if len(activities) >= MAX_ACTIVITIES:
        messages.append(
            "Notification limit reached. There may be more activities; to see\n"
            "them, log in to the web app.")

    return activity_query.all()


def process():
    config = get_config("notification.yaml")
    while True:
        n_sent = 0
        with model.session_scope() as session:
            interval = extract('epoch', func.now() - model.AppUser.email_time)
            user_list = (session.query(model.AppUser, func.now())
                .filter(model.AppUser.enabled,
                        model.AppUser.email_interval != 0,
                        (model.AppUser.email_time == None) |
                        (interval > model.AppUser.email_interval))
                .all())

            for user, now in user_list:
                messages = []
                activities = get_activities(session, user, now, messages)
                if len(activities) > 0:
                    send_email(config, user, activities, messages)
                user.email_time = now
                # Commit after each email to avoid multiple emails in case a
                # later iteration fails
                session.commit()

        log.info("Job finished. %d notification emails sent.", n_sent)
        time.sleep(config.JOB_INTERVAL_SECONDS)


def connect_db():
    model.connect_db(os.environ.get('DATABASE_URL'))


if __name__ == "__main__":
    try:
        log.info("Starting notification service: %s", datetime.datetime.utcnow())
        connect_db()
        time.sleep(interval)
        process()
    except KeyboardInterrupt:
        log.info("Shutting down due to user request (e.g. Ctrl-C)")
