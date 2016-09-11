import datetime
from email.mime.text import MIMEText
import logging
import os
import sys
import time

from sqlalchemy import extract, func

import activity
import config as app_config
from mail import send
import model
import utils


logging.basicConfig(format='%(asctime)s %(message)s')
log = logging.getLogger('app.notifications')
log.setLevel(logging.INFO)

STARTUP_DELAY = 60


def mail_content(config, activities):
    content = ''
    template_bc = config['MESSAGE_BROADCAST']
    template_std = config['MESSAGE_STANDARD']
    for act in activities:
        if 'broadcast' in act.verbs:
            template = template_bc
        else:
            template = template_std

        content += template.format(
            user_name=act.subject.name, message=act.message,
            ob_type=ob_type(act), verbs=verbs(act),
            date=config['DATE_FORMAT'].format(act.created))
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
        if i > 0 and i == len(action.verbs) - 1:
            expr += " and "
        elif i > 0:
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


def send_email(config, user, activities, messages, app_name_short):
    template = config['MESSAGE_CONTENT']
    params = {
        'user_id': user.id,
        'app_name_short': app_name_short}
    subject = config['MESSAGE_SUBJECT'].format(**params)
    params['activities'] = mail_content(config, activities)
    params['messages'] = "\n".join(messages)
    msg = MIMEText(template.format(**params), 'plain')
    msg['Subject'] = subject

    send(config, msg, user.email)


def send_error(config, errors):

    template = config['ERROR_CONTENT']
    msg = MIMEText(template.format(message=errors), 'plain')
    msg['Subject'] = config['ERROR_SUBJECT']

    send(config, msg, config['ERROR_SEND_TO'])


def get_activities(session, user, until_date, messages, limit, date_template):
    activities = activity.Activities(session)
    from_date = user.email_time
    earliest_from_date = until_date - datetime.timedelta(days=15)

    if from_date is None:
        from_date = until_date - datetime.timedelta(seconds=user.email_interval)

    if not from_date.tzinfo:
        from_date = from_date.replace(tzinfo=until_date.tzinfo)

    if from_date < earliest_from_date:
        messages.append(
            "Requested start date was too early {}.".format(
                date_template.format(from_date)))
        from_date = earliest_from_date

    messages.append(
        "Showing events from {}. All times are in UTC.".format(
            date_template.format(from_date)))

    activity_query = activities.timeline_query(
        user.id, from_date, until_date, {'at_top'})

    activity_query = activity_query.limit(limit)
    activities = list(activity_query.all())
    if len(activities) >= limit:
        messages.append(
            "Notification limit reached. There may be more activities; to see\n"
            "them, log in to the web app.")

    return activities


def process_once(config):
    rate_limit_interval = 1.0 / config.get('MAX_EMAILS_PER_SECOND', 10)
    n_sent = 0
    with model.session_scope() as session:
        interval = extract('epoch', func.now() - model.AppUser.email_time)
        user_list = (session.query(model.AppUser, func.now())
            .join(model.Organisation)
            .filter(model.AppUser.deleted != True,
                    model.Organisation.deleted != True,
                    model.AppUser.email_interval != 0,
                    (model.AppUser.email_time == None) |
                    (interval > model.AppUser.email_interval))
            .all())

        app_name_short = app_config.get_setting(session, 'app_name_short')

        for user, now in user_list:
            messages = []
            activities = get_activities(
                session, user, now, messages, config['MAX_ACTIVITIES'],
                config['DATE_FORMAT'])
            if len(activities) > 0:
                send_email(
                    config, user, activities, messages, app_name_short)
                n_sent += 1
            user.email_time = now
            # Commit after each email to avoid multiple emails in case a
            # later iteration fails
            session.commit()

            log.debug("Sleeping for %ds", rate_limit_interval)
            time.sleep(rate_limit_interval)

    log.info("Job finished. %d notification emails sent.", n_sent)
    return n_sent


def process_loop():
    config = utils.get_config("notification.yaml")
    try:
        while True:
            process_once(config)
            log.info("Sleeping for %ds", config['JOB_INTERVAL_SECONDS'])
            time.sleep(config['JOB_INTERVAL_SECONDS'])
    except Exception as e:
        send_error(config,
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
