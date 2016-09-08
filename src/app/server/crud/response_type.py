import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.orm import joinedload

from activity import Activities
import crud
import handlers
import logging
import model
from score import Calculator
from utils import falsy, keydefaultdict, reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.response_type')


class ResponseTypeHandler(
        handlers.Paginate, crud.program.ProgramCentric, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, response_type_id):
        '''Get single response type'''
        # print('GET', response_type_id)
        if not response_type_id:
            self.query()
            return

        with model.session_scope() as session:
            response_type = (session.query(model.ResponseType)
                .get((response_type_id, self.program_id)))
            if not response_type:
                raise handlers.MissingDocError("No such response type")
            to_son = ToSon(
                r'/id$',
                r'/name$',
                r'/parts$',
                r'/parts/.*',
                r'/formula$',
                r'/n_measures$',
            )
            son = to_son(response_type)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        '''Get a list.'''
        with model.session_scope() as session:
            query = (session.query(model.ResponseType)
                .filter(model.ResponseType.program_id == self.program_id)
                .order_by(model.ResponseType.name))
            query = self.paginate(query)
            rts = query.all()

            to_son = ToSon(
                r'/id$',
                r'/name$',
                r'/n_measures$',
                r'/[0-9]+$',
            )
            sons = to_son(rts)

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
            response_type = model.ResponseType(program=program)
            session.add(response_type)
            self._update(response_type, self.request_son)
            session.flush()
            response_type_id = str(response_type.id)
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
            self._update(response_type, self.request_son)
        self.get(response_type_id)

    def _update(self, measure, son):
        '''Apply user-provided data to the saved model.'''
        update = updater(measure)
        update('name', son)
        update('parts', son)
        update('formula', son)
