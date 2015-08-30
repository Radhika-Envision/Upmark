import logging
import os

import boto3


log = logging.getLogger('app.aws')
session = None


class StorageError(Exception):
    pass


def initialise_session():
    global session
    global region_name

    storage = os.environ.get('FILE_STORAGE', 'DATABASE')
    if storage != 'S3':
        log.info("Using database storage for new files")
        session = None
        return

    aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID', '')
    aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    region_name = os.environ.get('AWS_REGION_NAME', '')

    if (aws_access_key_id == ''
            or aws_secret_access_key == ''
            or region_name == ''):
        raise StorageError(
            "S3 Environment variable is missing")

    log.info("Using AWS S3 storage for new files. Region: %s", region_name)

    session = boto3.session.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region_name)


initialise_session()
