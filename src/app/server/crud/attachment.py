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
                    raise ValueError("No such object")

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
                    raise ValueError("No such object")

                self._check_authz(attachment)

                session.delete(attachment)
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such attachment")

        self.set_header("Content-Type", "text/plain")
        self.write(attachment_id)
        self.finish()

    def _check_authz(self, attachment):
        if not self.has_privillege('consultant'):
            if attachment.organisation.id != self.organisation.id:
                raise handlers.AuthzError(
                    "You can't modify another organisation's response")


class ResponseAttachmentsHandler(handlers.Paginate, handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def post(self, assessment_id, measure_id):
        fileinfo = self.request.files['file'][0]
        with model.session_scope() as session:
            assessment = session.query(model.Assessment).filter_by(id=assessment_id).one()

            self._check_authz(assessment)

            response = session.query(model.Response).filter_by(assessment_id=assessment_id, measure_id=measure_id).one()
            attachment = model.Attachment()
            attachment.organisation_id = assessment.organisation_id
            attachment.response_id = response.id
            attachment.file_name = fileinfo["filename"]
            attachment.blob = bytes(fileinfo['body'])
            session.add(attachment)
        self.set_header("Content-Type", "text/plain")
        self.write(attachment.id)
        self.finish()

    @tornado.web.authenticated
    def get(self, assessment_id, measure_id):
        with model.session_scope() as session:
            response = session.query(model.Response).filter_by(assessment_id=assessment_id, measure_id=measure_id).one()

            self._check_authz(response.assessment)

            query = session.query(model.Attachment).filter_by(response_id=response.id)

            to_son = ToSon(include=[
                r'/id$',
                r'/file_name$',
                r'/url$',
                # Descend
                r'/[0-9]+$'

            ])
            log.info("to_son: %s", to_son)
            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    def _check_authz(self, assessment):
        if not self.has_privillege('consultant'):
            if assessment.organisation.id != self.organisation.id:
                raise handlers.AuthzError(
                    "You can't modify another organisation's response")
