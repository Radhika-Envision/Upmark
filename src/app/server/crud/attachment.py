import os
import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy import func
from sqlalchemy.orm import joinedload

import crud.survey
import handlers
import model
import logging
import boto3

from utils import reorder, ToSon, truthy, updater
from tornado import gen
from tornado.web import asynchronous
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor


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

            storage = os.environ.get('FILE_STORAGE', 'DATABASE')
            if storage == 'S3':
                aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID', '')
                aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
                region_name = os.environ.get('REGION_NAME', '')

                if aws_access_key_id == '' or aws_secret_access_key == '' or region_name == '':
                    raise handlers.MissingDocError("S3 Environment variable is missing")

                boto_session = boto3.session.Session(aws_access_key_id=aws_access_key_id,
                                                     aws_secret_access_key=aws_secret_access_key,
                                                     region_name=region_name)

                s3 = boto_session.resource('s3')
                s3_path = "{0}/{1}/{2}".format(assessment_id, measure_id, fileinfo["filename"])
                s3_result = s3.Bucket('aquamark').put_object(Key=s3_path, Body=bytes(fileinfo['body']))

            attachment = model.Attachment()
            attachment.organisation_id = response.assessment.organisation_id
            attachment.response_id = response.id
            attachment.file_name = fileinfo["filename"]
            if storage == 'S3':
                attachment.storage = "aws"
                attachment.url = s3_result.website_redirect_location
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

            to_son = ToSon(include=[
                r'/id$',
                r'/file_name$',
                r'/url$',
                # Descend
                r'/[0-9]+$'
            ])
            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    def _check_authz(self, assessment):
        if not self.has_privillege('consultant'):
            if assessment.organisation.id != self.organisation.id:
                raise handlers.AuthzError(
                    "You can't modify another organisation's response")
