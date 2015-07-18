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

from utils import to_dict, reorder

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

            survey_son = to_dict(self.survey, include={'id', 'title'})
            son = to_dict(hierarchy, include={
                'id', 'title', 'seq', 'description'})
            son['survey'] = survey_son
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

            for ob in query.all():
                son = to_dict(ob, include={'id', 'title'})
                sons.append(son)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('author')
    def post(self, hierarchy_id):
        '''Create new.'''
        if hierarchy_id != '':
            raise handlers.MethodError("Can't use POST for existing object")

        self.check_editable()

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                hierarchy = model.Hierarchy(survey_id=self.survey_id)
                self._update(hierarchy, son)
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

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                hierarchy = session.query(model.Hierarchy)\
                    .get((hierarchy_id, self.survey_id))
                if hierarchy is None:
                    raise ValueError("No such object")
                self._update(hierarchy, son)
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
        if son.get('title', '') != '':
            hierarchy.title = son['title']
        if son.get('description', '') != '':
            hierarchy.description = son['description']
        if son.get('levels') != None:
            try:
                levels = [{
                    'title': str(l['title']),
                    'initial': str(l['initial'])[:2]
                } for l in son['levels']]
            except Exception:
                raise handlers.ModelError("Could not parse levels")
            hierarchy.levels = son['levels']
