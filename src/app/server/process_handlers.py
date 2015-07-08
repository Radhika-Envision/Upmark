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


class ProcessHandler(handlers.Paginate, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, process_id):
        '''
        Get a single process.
        '''
        log.info(process_id)
        if process_id == "":
            function_id = self.get_argument('function_id', None)
            if function_id == None:
                raise handlers.MethodError("Can't GET process without function_id.")

            self.query(function_id)
            return


        with model.session_scope() as session:
            try:
                process = session.query().get(process_id)
                if process is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such process")

            son = to_dict(process, include={'id', 'title', 'seq', 'description'})
            son = simplify(son)
            son = normalise(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self, function_id):
        '''
        Get a list of processs.
        '''

        sons = []
        with model.session_scope() as session:
            query = session.query(model.Process).filter(model.Process.function_id == function_id)

            # org_id = self.get_argument("org_id", None)
            # if org_id is not None:
            #     query = query.filter_by(organisation_id=org_id)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Process.title.ilike(r'%{}%'.format(term)))

            query = query.order_by(model.Process.title)
            query = self.paginate(query)

            for ob in query.all():
                son = to_dict(ob, include={'id', 'title', 'seq', 'description'})
                son = simplify(son)
                son = normalise(son)
                sons.append(son)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('author')
    def post(self, process_id):
        '''
        Create a new process.
        '''
        if process_id != '':
            raise handlers.MethodError("Can't use POST for existing process.")

        function_id = self.get_argument('function_id', None)
        if function_id == None:
            raise handlers.MethodError("Can't use POST process without function_id.")

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                process = model.Process()
                self._update(process, son)
                process.function_id = function_id
                session.add(process)
                session.flush()
                session.expunge(process)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.finish(str(process.id))

    @handlers.authz('author')
    def put(self, process_id):
        '''
        Update an existing process.
        '''
        if process_id == '':
            raise handlers.MethodError(
                "Can't use PUT for new process (no ID).")
        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                process = session.query(model.Process).get(process_id)
                if process is None:
                    raise ValueError("No such object")
                self._update(process, son)
                session.add(process)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such process")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(process_id)

    def _update(self, process, son):
        '''
        Apply process-provided data to the saved model.
        '''
        if son.get('title', '') != '':
            process.title = son['title']
        if son.get('seq', '') != '':
            process.seq = son['seq']
        if son.get('description', '') != '':
            process.description = son['description']
        if son.get('branch', '') != '':
            process.branch = son['branch']
        if son.get('function_id', '') != '':
            process.function_id = son['function_id']
