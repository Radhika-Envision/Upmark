import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.orm import joinedload

import handlers
import model
import logging

import crud
from utils import falsy, reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.response')


class ResponseHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, assessment_id, measure_id):
        '''Get a single response.'''

        with model.session_scope() as session:
            query = (session.query(model.Response).filter_by(
                    assessment_id=assessment_id, measure_id=measure_id))
            response = query.first()

            if response is None:
                raise handlers.MissingDocError("No such response")

            to_son = ToSon(include=[
                # Fields to match from any visited object
                r'/id$',
                r'/title$',
                # Fields to match from only the root object
                r'^/assessment_id$',
                r'^/measure_id$',
                r'^/comment$',
                r'^/response_parts.*$',
                r'^/not_relevant$',
                r'^/attachments$',
                r'^/audit_reason$',
                # Descend
                r'/parent$',
                r'/measure$',
                r'/assessment$',
            ], exclude=[
                # The IDs of rnodes and responses are not part of the API
                'r/^id$/',
                'r/parent/id$'
            ])
            son = to_son(response)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def put(self, assessment_id, measure_id):
        '''Save (create or update).'''

        try:
            with model.session_scope() as session:
                assessment = (session.query(model.Assessment)
                    .get(assessment_id))
                if assessment is None:
                    raise handlers.MissingDocError("No such assessment")

                if not self.has_privillege('consultant'):
                    if assessment.organisation.id != self.organisation.id:
                        raise handlers.AuthzError(
                            "You can't modify another organisation's response")

                query = (session.query(model.Response).filter_by(
                     assessment_id=assessment_id, measure_id=measure_id))
                response = query.first()

                if response is None:
                    measure = (session.query(model.Measure)
                        .get((measure_id, assessment.survey.id)))
                    if measure is None:
                        raise handlers.MissingDocError("No such measure")
                    response = model.Response(
                        assessment_id=assessment_id, measure_id=measure_id,
                        survey_id=assessment.survey.id)
                    session.add(response)

                self._update(response, self.request_son)
                self._update_score(response, session)

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(assessment_id, measure_id)

    def _update(self, response, son):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(response)
        update('comment', son)
        update('not_relevant', son)
        response.response_parts = son['response_parts']

        response.user_id = self.current_user.id
        update('audit_reason', son)

        # TODO: attachments
        response.attachments = []

    def _update_score(self, response, session):
        # TODO
        pass
