from concurrent.futures import ThreadPoolExecutor
import datetime
import time
import uuid

from tornado import gen
from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.session import make_transient

import crud.survey
import handlers
import model
import logging

from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.statistics')

MAX_WORKERS = 4


class AssessmentHandler(handlers.Paginate, handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    def get(self, assessment_id):
        if assessment_id == '':
            self.query()
            return

        with model.session_scope() as session:
            try:
                assessment = session.query(model.Assessment)\
                    .get(assessment_id)

                if assessment is None:
                    raise ValueError("No such object")
                if assessment.organisation.id != self.organisation.id:
                    self.check_privillege('author', 'consultant')
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such assessment")

            to_son = ToSon(include=[
                # Any
                r'/id$',
                r'/title$',
                r'/name$',
                r'/description$',
                r'/approval$',
                r'/n_measures$',
                # Nested
                r'/survey$',
                r'/organisation$',
                r'/hierarchy$',
                r'/hierarchy/structure.*$'
            ])
            son = to_son(assessment)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()
