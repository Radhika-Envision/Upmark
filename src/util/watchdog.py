#!/usr/bin/env python3

import argparse
import smtplib
import yaml
import datetime

from email.mime.text import MIMEText
from docker import Client
from dateutil.parser import parse

def check_docker(args):

    c = Client(base_url='unix://var/run/docker.sock')
    try:
        info = c.inspect_container('aq')
    except docker.errors.NotFound as e:
        raise

    started_at = parse(info['State']['StartedAt'])
    running = parse(info['State']['Running'])

    try:
        with open("watchdog-state.yaml", 'r') as f:
            state = yaml.load(f)
    except FileNotFoundError:
        state = {}
    if state is None:
        state = {}

    if state.get('emailed', None) is None:
        state['emailed'] = False

    if state.get('started_at', None) is None:
        state['started_at'] = None
    else:
        state['started_at'] = parse(state['started_at'])

    if not state['emailed']:
        if started_at > state['started_at']:
            send_email()
            state['emailed'] = True
            state['started_at'] = started_at
    else:
        if running and started_at - datetime.timedelta(minutes=1) > state['started_at']:
            state['emailed'] = False
            state['stated_at'] = started_at
        #print("send email")
        #send_email(None)

    state['started_at'] = str(state['started_at'])

    with open("watchdog-state.yaml", 'w') as f:
        yaml.dump(state, f)


def send_email():

    with open("watchdog.yaml", 'r') as stream:
        config = yaml.load(stream)

    msg = MIMEText(config['MESSAGE_CONTENT'])

    msg['Subject'] = config['MESSAGE_SUBJECT']
    msg['From'] = config['MESSAGE_SEND_FROM']
    msg['To'] = str(config['MESSAGE_SEND_TO'])

    smtp = smtplib.SMTP(config['SMTP_SERVER'])
    smtp.login(config['SMTP_USERNAME'], config['SMTP_PASSWORD'])
    smtp.sendmail(config['MESSAGE_SEND_FROM'], config['MESSAGE_SEND_TO'], msg.as_string())
    smtp.quit()


# def run(argv):
#     subparsers = parser.add_subparsers()

#     subparser = subparsers.add_parser('--test')
#     subparser.set_defaults(func=modify_user)

#     subparser = subparsers.add_parser('--send')
#     subparser.set_defaults(func=modify_org)

#     args = parser.parse_args(argv)
#     args.func(args)


if __name__ == '__main__':
    check_docker(None)
