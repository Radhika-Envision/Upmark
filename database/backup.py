import datetime
import logging
import os
import time

import boto3


class ConfigError(Exception):
    pass


session = None

logging.basicConfig(format='%(asctime)s %(message)s')
log = logging.getLogger('app.backup')
log.setLevel(logging.INFO)


def last_backup_time(identifier, now):
    client = session.client('rds')
    response = client.describe_db_snapshots(
        DBInstanceIdentifier=identifier,
    )
    response = [r for r in response["DBSnapshots"]
                if r["DBSnapshotIdentifier"].lower().startswith("weekly")]

    if not response:
        return None

    last_snapshot = min(response, key=lambda r: r.get('SnapshotCreateTime', now))
    return last_snapshot['SnapshotCreateTime'].replace(tzinfo=None)


def create_weekly_backup(identifier, now):
    client = session.client('rds')
    client.create_db_snapshot(
        DBSnapshotIdentifier='WeeklyBackup-{0:04d}-{1:02d}-{2:02d}'.format(
            now.year, now.month, now.day),
        DBInstanceIdentifier=identifier,
    )


def process_once():
    identifier = os.environ.get('AWS_RDS_IDENTIFIER', '')
    now = datetime.datetime.now().replace(tzinfo=None)
    last_time = last_backup_time(identifier, now)
    week_ago = now + datetime.timedelta(days=-7)
    if last_time is None or last_time < week_ago:
        create_weekly_backup(identifier, now)


def process_loop():
    interval = int(os.environ.get('BACKUP_CRON_INTERVAL', '300'))
    while True:
        try:
            process_once()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log.error("Failure during backup", exc_info=True)
        log.info("Sleeping for %ds", interval)
        time.sleep(interval)


def initialise_session():
    global session
    aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID', '')
    aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    region_name = os.environ.get('AWS_REGION_NAME', '')

    if aws_access_key_id == '':
        raise ConfigError("Missing access key")
    if aws_secret_access_key == '':
        raise ConfigError("Missing secret key")
    if region_name == '':
        raise ConfigError("Missing region key")

    session = boto3.session.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region_name)


if __name__ == '__main__':
    initialise_session()
    time.sleep(3)
    process_loop()
