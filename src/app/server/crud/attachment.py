import logging
import datetime
import os
import time
import uuid
import hashlib
import tempfile

import boto3
import botocore
from tornado.escape import json_decode, json_encode
from tornado import gen
import tornado.web
from tornado.web import asynchronous
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor
import sqlalchemy
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from parse import parse

import aws
import handlers
import model
from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.attachment')

MAX_WORKERS = 4


class AttachmentHandler(handlers.Paginate, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, attachment_id):
        with model.session_scope() as session:
            try:
                attachment = session.query(model.Attachment)\
                    .get(attachment_id)

                if attachment is None:
                    raise handlers.MissingDocError("No such attachment")

                self._check_authz(attachment)

                file_name = attachment.file_name
                if attachment.storage == "aws":
                    s3 = aws.session.client('s3', verify=False)
                    attachment_object = parse(aws.s3_url, attachment.url)
                    with tempfile.NamedTemporaryFile() as temp:

                        s3.download_file(attachment_object["bucket"],
                                               attachment_object["s3_path"],
                                               temp.name)

                        with open(temp.name, "rb") as file:
                            blob = file.read()
                else:
                    blob = attachment.blob
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such attachment")

        self.set_header('Content-Type', 'application/octet-stream')
        self.set_header('Content-Disposition', 'attachment; filename=' + file_name)
        self.write(bytes(blob))
        self.finish()

    @tornado.web.authenticated
    def delete(self, attachment_id):
        with model.session_scope() as session:
            try:
                attachment = session.query(model.Attachment)\
                    .get(attachment_id)

                if attachment is None:
                    raise handlers.MissingDocError("No such attachment")

                self._check_authz(attachment)

                session.delete(attachment)
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such attachment")

        self.finish()

    def _check_authz(self, attachment):
        if not self.has_privillege('consultant'):
            if attachment.organisation.id != self.organisation.id:
                raise handlers.AuthzError(
                    "You can't modify another organisation's response")


class ResponseAttachmentsHandler(handlers.Paginate, handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    def put(self, assessment_id, measure_id):
        son = self.request_son
        externals = son["externals"]
        with model.session_scope() as session:
            response = (session.query(model.Response)
                    .filter_by(assessment_id=assessment_id,
                                measure_id=measure_id)
                    .first())

            if response is None:
                raise handlers.MissingDocError("No such response")

            self._check_authz(response.assessment)

            for external in externals:
                url = external.get('url', '').strip()
                file_name = external.get('file_name', '').strip()
                if url == '' and file_name == '':
                    continue
                if url == '':
                    raise handlers.ModelError(
                        "URL required for link '%s'" % file_name)
                attachment = model.Attachment()
                attachment.organisation_id = response.assessment.organisation_id
                attachment.response_id = response.id
                attachment.url = url
                attachment.file_name = file_name
                attachment.storage = "external"

                session.add(attachment)
        self.get(assessment_id, measure_id)


    @tornado.web.authenticated
    @gen.coroutine
    def post(self, assessment_id, measure_id):
        fileinfo = self.request.files['file'][0]
        with model.session_scope() as session:
            response = (session.query(model.Response)
                    .filter_by(assessment_id=assessment_id,
                               measure_id=measure_id)
                    .first())

            if response is None:
                raise handlers.MissingDocError("No such response")

            self._check_authz(response.assessment)

            if aws.session is not None:
                s3 = aws.session.resource('s3', verify=False)
                bucket = os.environ.get('AWS_BUCKET')
                hex_key = hashlib.sha256(bytes(fileinfo['body'])).hexdigest()
                s3_path = "{0}/{1}".format(
                    response.assessment.organisation_id, hex_key)

                # Metadata can not contain non-ASCII characters - so encode
                # higher Unicode characters :/
                # https://github.com/boto/boto3/issues/478#issuecomment-180608544
                file_name_enc = (fileinfo["filename"]
                    .encode('ascii', errors='backslashreplace')
                    .decode('ascii')
                    [:1024])

                try:
                    s3.Bucket(bucket).put_object(
                        Key=s3_path,
                        Metadata={'filename': file_name_enc},
                        Body=bytes(fileinfo['body']))
                except botocore.exceptions.ClientError as e:
                    raise handlers.InternalModelError(
                        "Failed to write to data store", log_message=str(e))

            attachment = model.Attachment()
            attachment.organisation_id = response.assessment.organisation_id
            attachment.response_id = response.id
            attachment.file_name = fileinfo["filename"]

            if aws.session is not None:
                attachment.storage = "aws"
                aws_url = aws.s3_url.format(
                            region=aws.region_name,
                            bucket=bucket,
                            s3_path=s3_path)
                attachment.url = aws_url
            else:
                attachment.storage = "database"
                attachment.blob = bytes(fileinfo['body'])
            session.add(attachment)
            session.flush()


            attachment_id = str(attachment.id)

        self.set_header("Content-Type", "text/plain")
        self.write(attachment_id)
        self.finish()

    @tornado.web.authenticated
    def get(self, assessment_id, measure_id):
        with model.session_scope() as session:
            response = (session.query(model.Response)
                    .filter_by(assessment_id=assessment_id,
                               measure_id=measure_id)
                    .first())

            if response is None:
                raise handlers.MissingDocError("No such response")

            self._check_authz(response.assessment)

            query = (session.query(model.Attachment)
                    .filter_by(response_id=response.id))

            to_son = ToSon(
                r'/id$',
                r'/file_name$',
                r'/url$'
            )
            # Don't send internal URLs to client
            to_son_internal = ToSon(
                r'/id$',
                r'/file_name$'
            )

            sons = []
            for attachment in query.all():
                if attachment.storage == 'external':
                    sons.append(to_son(attachment))
                else:
                    sons.append(to_son_internal(attachment))

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    def _check_authz(self, assessment):
        if not self.has_privillege('consultant'):
            if assessment.organisation.id != self.organisation.id:
                raise handlers.AuthzError(
                    "You can't modify another organisation's response")
