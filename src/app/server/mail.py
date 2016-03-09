import smtplib


def send(config, message, to_addrs):
    with smtplib.SMTP('{}:{}'.format(config['SMTP_SERVER'], config['SMTP_PORT'])) as smtp:
        if config['SMTP_USE_TLS']:
            smtp.starttls()
        smtp.login(config['SMTP_USERNAME'], config['SMTP_PASSWORD'])
        smtp.sendmail(config['MESSAGE_SEND_FROM'], to_addrs, message.as_string())
