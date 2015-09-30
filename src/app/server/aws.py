import logging
import os

import boto3
import certifi


log = logging.getLogger('app.aws')
session = None
s3_url = "https://s3-{region}.amazonaws.com/{bucket}/{s3_path}"

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

    # Try to connect just to check that the credentials are OK. If not, this
    # will throw an exception during initialisation and the web server should
    # fail to start.
    session.resource('s3').Bucket('aquamark').load()


def monkeypatch_method(cls):
    '''
    Guido's mokeypatching decorator:
    https://mail.python.org/pipermail/python-dev/2008-January/076194.html
    '''
    def decorator(func):
        setattr(cls, func.__name__, func)
        return func
    return decorator


def patch_session_certifi():
    '''
    Recent versions of certifi (dependency of Tornado) do not allow
    cross-signed certificates, which causes boto to fail with

        botocore.vendored.requests.exceptions.SSLError:
        [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed

    We pass a special verification method that uses the old behaviour. The
    old_where function is deprecated; when it is removed we will need to
    upgrade OpenSSL to 1.0.2, probably by upgrading the operating system used
    in the Dockerfile.

    For discussion, see:
    https://github.com/certifi/python-certifi/issues/26
    https://github.com/aws/aws-cli/issues/1499
    '''

    old_client = boto3.session.Session.client
    old_resource = boto3.session.Session.resource

    @monkeypatch_method(boto3.session.Session)
    def client(*args, **kwargs):
        if 'verify' not in kwargs:
            kwargs['verify'] = certifi.old_where()
        return old_client(*args, **kwargs)

    @monkeypatch_method(boto3.session.Session)
    def resource(*args, **kwargs):
        if 'verify' not in kwargs:
            kwargs['verify'] = certifi.old_where()
        return old_resource(*args, **kwargs)


patch_session_certifi()
initialise_session()
