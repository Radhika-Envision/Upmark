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


class SubprocessHandler(handlers.Paginate, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, subprocess_id):
        '''
        Get a single subprocess.
        '''
        log.info(subprocess_id)
        if subprocess_id == "":
            process_id = self.get_argument('process_id', None)
            if process_id == None:
                raise handlers.MethodError("Can't GET subprocess without process_id.")

            self.query(process_id)
            return


        with model.session_scope() as session:
            try:
                subprocess = session.query(model.Subprocess).get(subprocess_id)
                if subprocess is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such subprocess")

            son = to_dict(subprocess, include={'id', 'title', 'seq', 'description'})
            son = simplify(son)
            son = normalise(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self, process_id):
        '''
        Get a list of subprocesss.
        '''

        sons = []
        with model.session_scope() as session:
            query = session.query(model.Subprocess).filter(model.Subprocess.process_id == process_id)

            # org_id = self.get_argument("org_id", None)
            # if org_id is not None:
            #     query = query.filter_by(organisation_id=org_id)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Subprocess.title.ilike(r'%{}%'.format(term)))

            query = query.order_by(model.Subprocess.title)
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
    def post(self, subprocess_id):
        '''
        Create a new subprocess.
        '''
        if subprocess_id != '':
            raise handlers.MethodError("Can't use POST for existing subprocess.")

        process_id = self.get_argument('process_id', None)
        if process_id == None:
            raise handlers.MethodError("Can't use POST subprocess without process_id.")

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                subprocess = model.Subprocess()
                self._update(subprocess, son)
                subprocess.process_id = process_id
                session.add(subprocess)
                session.flush()
                session.expunge(subprocess)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.finish(str(subprocess.id))

    @handlers.authz('author')
    def put(self, subprocess_id):
        '''
        Update an existing subprocess.
        '''
        if subprocess_id == '':
            raise handlers.MethodError(
                "Can't use PUT for new subprocess (no ID).")
        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                subprocess = session.query(model.Subprocess).get(subprocess_id)
                if subprocess is None:
                    raise ValueError("No such object")
                self._update(subprocess, son)
                session.add(subprocess)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such subprocess")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(subprocess_id)

    def _update(self, subprocess, son):
        '''
        Apply subprocess-provided data to the saved model.
        '''
        if son.get('title', '') != '':
            subprocess.title = son['title']
        if son.get('seq', '') != '':
            subprocess.seq = son['seq']
        if son.get('description', '') != '':
            subprocess.description = son['description']
        if son.get('branch', '') != '':
            subprocess.branch = son['branch']
        if son.get('process_id', '') != '':
            subprocess.process_id = son['process_id']
