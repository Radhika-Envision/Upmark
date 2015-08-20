import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.orm import joinedload

import crud.survey
import handlers
import model
import logging

from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.rnode')


class ResponseNodeHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, assessment_id, qnode_id):
        if qnode_id == '':
            self.query(assessment_id)
            return

        raise handlers.MissingDocError("Not implemented.")

    def query(self, assessment_id):
        '''Get a list.'''
        parent_id = self.get_argument('parentId', '')
        if parent_id == '':
            raise handlers.ModelError("Parent qnode ID required")

        with model.session_scope() as session:
            assessment = (session.query(model.Assessment)
                .filter_by(id=assessment_id)
                .first())

            if assessment is None:
                raise handlers.MissingDocError("No such assessment")
            self._check_authz(assessment)

            rnode = (session.query(model.ResponseNode)
                .filter_by(assessment_id=assessment_id,
                           qnode_id=parent_id)
                .first())

            if rnode is None:
                children = []
            else:
                children = rnode.children

            exclude = [
                # The IDs of rnodes and responses are not part of the API
                r'^/[0-9]+/id$',
            ]
            if self.current_user.role in {'clerk', 'org_admin'}:
                exclude += [
                    r'/score$',
                ]

            to_son = ToSon(include=[
                # Fields to match from any visited object
                r'/id$',
                r'/score$',
                r'/n_submitted$',
                r'/n_reviewed$',
                r'/n_approved$',
                # Descend into nested objects
                r'/[0-9]+$',
                r'/qnode$',
            ], exclude=exclude)
            sons = to_son(children)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    def _check_authz(self, assessment):
        if not self.has_privillege('consultant'):
            if assessment.organisation.id != self.organisation.id:
                raise handlers.AuthzError(
                    "You can't modify another organisation's response")
