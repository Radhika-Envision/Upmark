import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.orm import joinedload

from activity import Activities
import crud.program
import handlers
import model
import logging
import voluptuous
from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.hierarchy')


class HierarchyHandler(crud.program.ProgramCentric, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, hierarchy_id):

        if hierarchy_id == '':
            self.query()
            return

        with model.session_scope() as session:
            try:
                hierarchy = session.query(model.Hierarchy)\
                    .get((hierarchy_id, self.program_id))

                if hierarchy is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such hierarchy")

            self.check_browse_program(session, self.program_id, hierarchy_id)

            to_son = ToSon(
                # Any
                r'/id$',
                r'/title$',
                r'/seq$',
                r'/created$',
                r'/deleted$',
                r'/is_editable$',
                r'/n_measures$',
                r'/program/tracking_id$',
                # Root-only
                r'<^/description$',
                r'^/structure.*',
                # Nested
                r'/program$',
            )
            son = to_son(hierarchy)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self):
        '''Get a list.'''
        with model.session_scope() as session:
            query = session.query(model.Hierarchy)\
                .filter_by(program_id=self.program_id)\
                .order_by(model.Hierarchy.title)

            deleted = self.get_argument('deleted', '')
            if deleted != '':
                deleted = truthy(deleted)
                query = query.filter(model.Hierarchy.deleted == deleted)

            to_son = ToSon(
                r'/id$',
                r'/title$',
                r'/deleted$',
                r'/n_measures$',
                # Descend
                r'/[0-9]+$'
            )
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
                hierarchy = model.Hierarchy(program_id=self.program_id)
                self._update(hierarchy, self.request_son)
                session.add(hierarchy)

                # Need to flush so object has an ID to record action against.
                session.flush()

                act = Activities(session)
                act.record(self.current_user, hierarchy, ['create'])
                if not act.has_subscription(self.current_user, hierarchy):
                    act.subscribe(self.current_user, hierarchy.program)
                    self.reason("Subscribed to program")

                hierarchy_id = str(hierarchy.id)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(hierarchy_id)

    @handlers.authz('author')
    def put(self, hierarchy_id):
        '''Update existing.'''
        if hierarchy_id == '':
            raise handlers.MethodError("Hierarchy ID required")

        self.check_editable()

        try:
            with model.session_scope() as session:
                hierarchy = session.query(model.Hierarchy)\
                    .get((hierarchy_id, self.program_id))
                if hierarchy is None:
                    raise ValueError("No such object")
                self._update(hierarchy, self.request_son)

                verbs = []
                if session.is_modified(hierarchy):
                    verbs.append('update')

                if hierarchy.deleted:
                    hierarchy.deleted = False
                    verbs.append('undelete')

                act = Activities(session)
                act.record(self.current_user, hierarchy, verbs)
                if not act.has_subscription(self.current_user, hierarchy):
                    act.subscribe(self.current_user, hierarchy.program)
                    self.reason("Subscribed to program")

        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such hierarchy")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(hierarchy_id)

    @handlers.authz('author')
    def delete(self, hierarchy_id):
        if hierarchy_id == '':
            raise handlers.MethodError("Hierarchy ID required")

        self.check_editable()

        try:
            with model.session_scope() as session:
                hierarchy = session.query(model.Hierarchy)\
                    .get((hierarchy_id, self.program_id))
                if hierarchy is None:
                    raise ValueError("No such object")

                act = Activities(session)
                if not hierarchy.deleted:
                    act.record(self.current_user, hierarchy, ['delete'])
                if not act.has_subscription(self.current_user, hierarchy):
                    act.subscribe(self.current_user, hierarchy.program)
                    self.reason("Subscribed to program")

                hierarchy.deleted = True

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError("This hierarchy is in use")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such hierarchy")

        self.finish()

    def _update(self, hierarchy, son):
        update = updater(hierarchy)
        update('title', son)
        update('description', son, sanitise=True)
        try:
            update('structure', son)
        except voluptuous.Error as e:
            raise handlers.ModelError("Structure is invalid: %s" % str(e))
