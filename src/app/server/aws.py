import logging
import os
import re

import boto3


log = logging.getLogger('app.aws')
session = None
s3_url = "https://s3-{region}.amazonaws.com/{bucket}/{s3_path}"
S3_PATTERN = re.compile(
    r'https://s3-(?P<region>[^./]+).amazonaws.com/'
    r'(?P<bucket>[^/]+)/(?P<path>.+)')

class StorageError(Exception):
    pass


def initialise_session():
    global session
    global region_name

    aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID', '')
    if aws_access_key_id == '':
        log.info("Using database storage for new files")
        session = None
        return

    aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    region_name = os.environ.get('AWS_REGION_NAME', '')

    if aws_secret_access_key == '' or region_name == '':
        raise StorageError(
            "S3 Environment variable is missing")

    log.info("Using AWS S3 storage for new files. Region: %s", region_name)

    session = boto3.session.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region_name)

    bucket_name = os.environ.get('AWS_BUCKET', '')

    # Try to connect just to check that the credentials are OK. If not, this
    # will throw an exception during initialisation and the web server should
    # fail to start.
    session.resource('s3').Bucket(bucket_name).load()


def monkeypatch_method(cls):
    '''
    Guido's mokeypatching decorator:
    https://mail.python.org/pipermail/python-dev/2008-January/076194.html
    '''
    def decorator(func):
        setattr(cls, func.__name__, func)
        return func
    return decorator


initialise_session()
