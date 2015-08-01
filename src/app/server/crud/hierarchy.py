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

from utils import reorder, ToSon, updater

log = logging.getLogger('app.data_access')


class HierarchyHandler(crud.survey.SurveyCentric, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, hierarchy_id):
        if hierarchy_id == "":
            self.query()
            return

        with model.session_scope() as session:
            try:
                hierarchy = session.query(model.Hierarchy)\
                    .get((hierarchy_id, self.survey_id))

                if hierarchy is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such hierarchy")

            to_son = ToSon(include=[
                # Any
                r'/id$',
                r'/title$',
                r'/seq$',
                # Root-only
                r'^/description$',
                # Nested
                r'/survey$',
            ])
            son = to_son(hierarchy)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self):
        '''Get a list.'''
        sons = []
        with model.session_scope() as session:
            query = session.query(model.Hierarchy)\
                .filter_by(survey_id=self.survey_id)\
                .order_by(model.Hierarchy.title)

            to_son = ToSon(include=[
                r'/id$',
                r'/title$',
            ])
            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('author')
    def post(self, hierarchy_id):
        '''Create new.'''
        if hierarchy_id != '':
            raise handlers.MethodError("Can't use POST for existing object")

        self.check_editable()

        try:
            with model.session_scope() as session:
                hierarchy = model.Hierarchy(survey_id=self.survey_id)
                self._update(hierarchy, self.request_son)
                session.add(hierarchy)
                session.flush()
                hierarchy_id = str(hierarchy.id)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(hierarchy_id)

    @handlers.authz('author')
    def put(self, hierarchy_id):
        '''Update existing.'''
        if hierarchy_id == '':
            raise handlers.MethodError("Hierarchy ID required")

        try:
            with model.session_scope() as session:
                hierarchy = session.query(model.Hierarchy)\
                    .get((hierarchy_id, self.survey_id))
                if hierarchy is None:
                    raise ValueError("No such object")
                self._update(hierarchy, self.request_son)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such hierarchy")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(hierarchy_id)

    @handlers.authz('author')
    def delete(self, hierarchy_id):
        if hierarchy_id == '':
            raise handlers.MethodError("Hierarchy ID required")
        try:
            with model.session_scope() as session:
                hierarchy = session.query(model.Hierarchy)\
                    .get((hierarchy_id, self.survey_id))
                if hierarchy is None:
                    raise ValueError("No such object")
                session.delete(hierarchy)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError("This hierarchy is in use")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such hierarchy")

        self.finish()

    def _update(self, hierarchy, son):
        update = updater(hierarchy)
        update('title', son)
        update('description', son)

        if son.get('levels') != None:
            try:
                levels = [{
                    'title': str(l['title']),
                    'initial': str(l['initial'])[:2],
                    'has_measures': truthy(l['has_measures'])
                } for l in son['levels']]
            except Exception:
                raise handlers.ModelError("Could not parse levels", )
            hierarchy.levels = son['levels']
