import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy import func
from sqlalchemy.orm import joinedload
import voluptuous.error

from activity import Activities
import crud
import handlers
import logging
import model
from response_type import ResponseTypeError
from score import Calculator
from utils import falsy, reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.response_type')


class ResponseTypeHandler(
        handlers.Paginate, crud.program.ProgramCentric, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, response_type_id):
        '''Get single response type'''
        if not response_type_id:
            self.query()
            return

        with model.session_scope() as session:
            response_type, count = (
                session.query(model.ResponseType, func.count(model.Measure.id))
                .outerjoin(model.Measure)
                .filter(model.ResponseType.id == response_type_id)
                .filter(model.ResponseType.program_id == self.program_id)
                .group_by(model.ResponseType.id, model.ResponseType.program_id)
                .first()) or (None, None)
            if not response_type:
                raise handlers.MissingDocError("No such response type")
            to_son = ToSon(
                r'/id$',
                r'/program_id$',
                r'/ob_type$',
                r'/name$',
                r'/title$',
                r'/parts$',
                r'/parts/.*',
                r'/formula$',
                r'/n_measures$',
                r'/program$',
                omit=True)
            son = to_son(response_type)
            son['nMeasures'] = count
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        '''Get a list.'''
        term = self.get_argument('term', None)

        with model.session_scope() as session:
            query = (
                session.query(model.ResponseType, func.count(model.Measure.id))
                .outerjoin(model.Measure)
                .filter(model.ResponseType.program_id == self.program_id)
                .group_by(model.ResponseType.id, model.ResponseType.program_id)
                .order_by(model.ResponseType.name))

            if term:
                query = query.filter(
                    model.ResponseType.name.ilike(r'%{}%'.format(term)))

            query = self.paginate(query)
            rtcs = query.all()

            to_son = ToSon(
                r'/id$',
                r'/name$',
            )
            to_son_extra = ToSon(
                r'/n_measures$',
                r'/n_parts$',
            )
            sons = []
            for rt, count in rtcs:
                rt_son = to_son(rt)
                extra = {
                    'n_parts': len(rt.parts),
                    'n_measures': count,
                }
                rt_son.update(to_son_extra(extra))
                sons.append(rt_son)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('author')
    def post(self, response_type_id):
        '''Create new'''
        if response_type_id:
            raise handlers.ModelError("Can't specify ID when creating")
        with model.session_scope() as session:
            program = session.query(model.Program).get(self.program_id)
            if not program:
                raise handlers.MissingDocError("No such program")

            rt_by_name = (session.query(model.ResponseType)
                .filter(model.ResponseType.program_id == self.program_id)
                .filter(model.ResponseType.name == self.request_son['name'])
                .first())
            if rt_by_name is not None:
                raise handlers.ModelError(
                    "A response type of that name already exists")

            response_type = model.ResponseType(program=program)
            session.add(response_type)
            try:
                self._update(response_type, self.request_son)
            except ResponseTypeError as e:
                raise handlers.ModelError(str(e))
            except voluptuous.error.Error as e:
                raise handlers.ModelError(str(e))

            try:
                session.flush()
            except sqlalchemy.exc.IntegrityError as e:
                raise handlers.ModelError.from_sa(e)

            response_type_id = str(response_type.id)
            # No need for survey update: RT is not being used yet

            act = Activities(session)
            act.record(self.current_user, response_type, ['create'])
            if not act.has_subscription(self.current_user, response_type):
                act.subscribe(self.current_user, response_type.program)
                self.reason("Subscribed to program")
        self.get(response_type_id)

    @handlers.authz('author')
    def delete(self, response_type_id):
        '''Delete'''
        with model.session_scope() as session:
            response_type = (session.query(model.ResponseType)
                .get((response_type_id, self.program_id)))
            if not response_type:
                raise handlers.MissingDocError("No such response type")
            session.delete(response_type)
            # No need for survey update: delete will fail if any measures are
            # using this RT

            act = Activities(session)
            act.record(self.current_user, response_type, ['delete'])
            if not act.has_subscription(self.current_user, response_type):
                act.subscribe(self.current_user, response_type.program)
                self.reason("Subscribed to program")
        self.set_header("Content-Type", "text/plain")
        self.finish()

    @handlers.authz('author')
    def put(self, response_type_id):
        '''Update existing'''
        with model.session_scope() as session:
            response_type = (session.query(model.ResponseType)
                .get((response_type_id, self.program_id)))
            if not response_type:
                raise handlers.MissingDocError("No such response type")

            rt_by_name = (session.query(model.ResponseType)
                .filter(model.ResponseType.program_id == self.program_id)
                .filter(model.ResponseType.name == self.request_son['name'])
                .first())
            if rt_by_name and rt_by_name != response_type:
                raise handlers.ModelError(
                    "A response type of that name already exists")

            try:
                self._update(response_type, self.request_son)
            except ResponseTypeError as e:
                raise handlers.ModelError(str(e))
            except voluptuous.error.Error as e:
                raise handlers.ModelError(str(e))

            verbs = []
            # Check if modified now to avoid problems with autoflush later
            if session.is_modified(response_type):
                verbs.append('update')
                calculator = Calculator.structural()
                for measure in response_type.measures:
                    for qnode_measure in measure.qnode_measures:
                        calculator.mark_measure_dirty(qnode_measure)
                calculator.execute()

            act = Activities(session)
            act.record(self.current_user, response_type, verbs)
            if not act.has_subscription(self.current_user, response_type):
                act.subscribe(self.current_user, response_type.program)
                self.reason("Subscribed to program")

        self.get(response_type_id)

    def _update(self, measure, son):
        '''Apply user-provided data to the saved model.'''
        if not son.get('name', None):
            raise handlers.ModelError("Name is required")
        update = updater(measure)
        update('name', son)
        update('parts', son)
        update('formula', son)
