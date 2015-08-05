#!/usr/bin/env python3

import argparse
import datetime
from email.mime.text import MIMEText
import inspect
import logging
import logging.config
import os
import tempfile
import smtplib
import socket
from string import Template
import sys
import docker

from docker import Client
from docker.utils import kwargs_from_env
from dateutil.parser import parse
import yaml
import pytz


log = logging.getLogger('watchdog')


def get_package_dir():
    frameinfo = inspect.getframeinfo(inspect.currentframe())
    return os.path.dirname(frameinfo.filename)


def get_config_path():
    return os.path.join(get_package_dir(), "watchdog.yaml")


logging.config.fileConfig(os.path.join(get_package_dir(), 'logging.cfg'))


def get_state_path():
    return os.path.join(tempfile.gettempdir(), "watchdog-state.yaml")


def reset():
    try:
        os.remove(get_state_path())
    except FileNotFoundError:
        pass


def get_config():
    log.debug("Reading config %s", get_config_path())
    with open(get_config_path(), 'r') as stream:
        return yaml.load(stream)


def get_docker_base_url():
    if os.environ.get('DOCKER_HOST'):
        return os.environ.get('DOCKER_HOST')
    return 'unix://var/run/docker.sock'


def get_docker_client():
    if os.environ.get('DOCKER_HOST'):
        cert_path = os.environ.get('DOCKER_CERT_PATH')
        log.debug("DOCKER_CERT_PATH: %s", os.path.join(cert_path, 'cert.pem'))
        tls_config = docker.tls.TLSConfig(
          client_cert=(os.path.join(cert_path, 'cert.pem'), os.path.join(cert_path, 'key.pem')), 
          verify=os.path.join(cert_path, 'ca.pem')
        )
        client = docker.Client(base_url=get_docker_base_url(), tls=tls_config)
        return client
    return Client(base_url=get_docker_base_url())

def get_container_log():
    config = get_config()
    c = get_docker_client()
    try:
        logs = c.logs(config['CONTAINER_NAME'], tail=config['N_LOG_LINES'])
    except docker.errors.NotFound as e:
        raise

    return logs.decode("utf-8")


def get_container_info():
    config = get_config()
    c = Client(base_url=get_docker_base_url())
    try:
        info = c.inspect_container(config['CONTAINER_NAME'])
    except docker.errors.NotFound as e:
        raise

    started_at = parse(info['State']['StartedAt']).replace(tzinfo = pytz.utc)
    running = info['State']['Running']
    return started_at, running


def load_state():
    try:
        with open(get_state_path(), 'r') as f:
            state = yaml.load(f)
    except FileNotFoundError:
        state = {}
    if state is None:
        state = {}

    return state


def save_state(state):
    with open(get_state_path(), 'w') as f:
        yaml.dump(state, f)


def check_docker():
    log.info("Checking state of application")

    config = get_config()
    started_at, running = get_container_info()
    log.debug("Container started_at: %s, running: %s", started_at, running)

    state = load_state()

    if 'status' not in state:
        log.debug("Current status is: starting up")
        log.info("Transitioning to: running")
        state['status'] = 'running'
        state['started_at'] = started_at

    elif state['status'] == 'running':
        log.debug("Current status is: running")
        if started_at.replace(tzinfo = pytz.utc) > state['started_at']:
            # Start time is different, so the machine crashed.
            log.info("Transitioning to: crashed")
            send_email('crashed', get_container_log())
            state['status'] = 'crashed'
            state['started_at'] = started_at

    elif running:
        log.debug("Current status is: crashed")
        delta = datetime.timedelta(milliseconds=config['MINIMUM_UPTIME_MS'])
        now = datetime.datetime.utcnow().replace(tzinfo = pytz.utc)
        if now - delta > state['started_at']:
            # Instance has been running for a while. Consider it to be running
            # well again.
            log.info("Transitioning to: running")
            send_email('recovered', get_container_log())
            state['status'] = 'running'
            state['started_at'] = started_at

    save_state(state)


def send_email(message_type, logs):
    log.info("Sending email '%s'", message_type)
    config = get_config()

    template = Template(config['MESSAGE_CONTENT_%s' % message_type.upper()])
    n_log_lines = config['N_LOG_LINES']
    msg = MIMEText(template.substitute(server=socket.gethostname(), logs=logs, n_log_lines=n_log_lines), 'text/plain')

    msg['Subject'] = config['MESSAGE_SUBJECT_%s' % message_type.upper()]
    msg['From'] = config['MESSAGE_SEND_FROM']
    msg['To'] = str(config['MESSAGE_SEND_TO'])

    _send(msg)


def _send(message):
    log.info("Communicating with SMTP server")
    config = get_config()
    with smtplib.SMTP(config['SMTP_SERVER']) as smtp:
        smtp.login(config['SMTP_USERNAME'], config['SMTP_PASSWORD'])
        smtp.sendmail(config['MESSAGE_SEND_FROM'], config['MESSAGE_SEND_TO'], message.as_string())


def run(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--test-email', action='store_true', default=False,
        help="Send a test email using the credentials in the config file")
    parser.add_argument(
        '--reset', action='store_true', default=False,
        help="Reset to the initial state")

    args = parser.parse_args(argv)

    try:
        get_config()
    except FileNotFoundError:
        print("Configuration file %s is missing." % get_config_path())
        print("Copy %s.SAMPLE and edit it." % get_config_path())
        sys.exit(1)

    if args.test_email:
        send_email('test', None)
    elif args.reset:
        reset()
    else:
        check_docker()


if __name__ == '__main__':
    run(sys.argv[1:])
