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

from utils import to_dict, simplify, normalise

log = logging.getLogger('app.data_access')


class FunctionHandler(handlers.Paginate, handlers.BaseHandler):

    # @tornado.web.authenticated
    def get(self, function_id):
        '''
        Get a single function.
        '''
        log.info(function_id)
        if function_id == "":
            self.query()
            return

        with model.session_scope() as session:
            try:
                function = session.query(model.Function).get(function_id)
                log.info(function)
                if function is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such function")

            son = to_dict(function, include={'id', 'title', 'seq', 'description'})
            son = simplify(son)
            son = normalise(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    # @tornado.web.authenticated
    def query(self):
        '''
        Get a list of functions.
        '''

        sons = []
        with model.session_scope() as session:
            query = session.query(model.Function)

            branch = self.get_argument("branch", None)
            if branch is not None:
                query = query.filter_by(branch=branch)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Function.title.ilike(r'%{}%'.format(term)))

            query = query.order_by(model.Function.title)
            query = self.paginate(query)

            for ob in query.all():
                son = to_dict(ob, include={'id', 'title', 'seq'})
                son = simplify(son)
                son = normalise(son)
                sons.append(son)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    # @handlers.authz('author')
    def post(self, function_id):
        '''
        Create a new function.
        '''
        if function_id != '':
            raise handlers.MethodError("Can't use POST for existing function.")

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                function = model.Function()
                self._update(function, son)
                function.branch = self.get_current_branch()
                session.add(function)
                session.flush()
                session.expunge(function)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(function.id)

    # @handlers.authz('author')
    def put(self, function_id):
        '''
        Update an existing function.
        '''
        if function_id == '':
            raise handlers.MethodError(
                "Can't use PUT for new function (no ID).")
        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                function = session.query(model.Function).get(function_id)
                if function is None:
                    raise ValueError("No such object")
                self._update(function, son)
                session.add(function)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such function")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(function_id)

    def _update(self, function, son):
        '''
        Apply function-provided data to the saved model.
        '''
        if son.get('title', '') != '':
            function.title = son['title']
        if son.get('seq', '') != '':
            function.seq = son['seq']
        if son.get('description', '') != '':
            function.description = son['description']
        if son.get('branch', '') != '':
            function.branch = son['branch']

    # TODO : we can save branch code somewhere global area 
    def get_current_branch(self):
        with model.session_scope() as session:
            survey = session.query(model.Survey).order_by(sqlalchemy.desc(model.Survey.created))[0]
            return survey.branch
