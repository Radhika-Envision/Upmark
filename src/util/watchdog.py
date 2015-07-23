#!/usr/bin/env python3

import argparse
import smtplib
import yaml

from email.mime.text import MIMEText
from docker import Client

def check_docker(args):

    c = Client(base_url='unix://var/run/docker.sock')
    create_date = c.inspect_container('aq')['Created']
    start_date = c.inspect_container('aq')['State']['FinishedAt']

    if create_date > start_date:
        send_email(None)


def send_email(args):

    with open("watchdog.yml", 'r') as stream:
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