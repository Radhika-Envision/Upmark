import uuid
import json

from tornado import gen
from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy

import handlers
import model
import logging

from utils import reorder, ToSon, truthy, updater

log = logging.getLogger('app.statistics_handler')

class ReportHandler(handlers.Paginate, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self):
        assessment1 = self.get_argument("assessment1", None)
        assessment2 = self.get_argument("assessment2", None)
        response = []
        with model.session_scope() as session:
            try:
                a1 = session.query(model.Assessment)\
                    .get(assessment1)

                if a1 is None:
                    raise ValueError("No such object")

                a2 = session.query(model.Assessment)\
                    .get(assessment2)

                if a2 is None:
                    raise ValueError("No such object")

            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such survey")

            to_son = ToSon(include=[
                    # Fields to match from any visited object
                    r'/id$',
                    r'/title$'
            ])

            if not(a1 is None or a2 is None):
                son1 = to_son(a1)
                son2 = to_son(a2)
                response.append(son1)
                response.append(son2)

            self.set_header("Content-Type", "application/json")
            self.write(json_encode(response))
            self.finish()
