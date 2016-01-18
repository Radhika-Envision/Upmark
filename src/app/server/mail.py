import smtplib


def send(config, message):
    with smtplib.SMTP('{}:{}'.format(config['SMTP_SERVER'], config['SMTP_PORT'])) as smtp:
        smtp.login(config['SMTP_USERNAME'], config['SMTP_PASSWORD'])
        smtp.sendmail(config['MESSAGE_SEND_FROM'], message['To'], message.as_string())
