import logging
import inspect
import os
import yaml
import smtplib

log = logging.getLogger("app.mail")

def get_package_dir():
    frameinfo = inspect.getframeinfo(inspect.currentframe())
    return os.path.dirname(frameinfo.filename)


def get_config_path(yaml_file_name):
    return os.path.join(get_package_dir(), yaml_file_name)

def get_config(yaml_file_name):
    with open(get_config_path(yaml_file_name), 'r') as stream:
        return yaml.load(stream)

def send(config, message):
    with smtplib.SMTP('{}:{}'.format(config['SMTP_SERVER'], config['SMTP_PORT'])) as smtp:
        smtp.login(config['SMTP_USERNAME'], config['SMTP_PASSWORD'])
        smtp.sendmail(config['MESSAGE_SEND_FROM'], message['To'], message.as_string())
