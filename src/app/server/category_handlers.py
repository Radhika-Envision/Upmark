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

    # test using curl
    # curl --cookie "_xsrf=2|d8b3038c|399eda1c903e9de19748e529c10603d3|1434072137" \
    # -H "X-Xsrftoken:2|d8b3038c|399eda1c903e9de19748e529c10603d3|1434072137" \
    # http://192.168.59.103:8000/function.json or
    # http://192.168.59.103:8000/function/67f5e799-b32e-492f-86dc-3dc29cb127fe.json
    # @handlers.authz('author')
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

            son = to_dict(function, include={'id', 'title'})
            son = simplify(son)
            son = normalise(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    # @handlers.authz('author')
    def query(self):
        '''
        Get a list of functions.
        '''

        sons = []
        with model.session_scope() as session:
            query = session.query(model.Function)

            # org_id = self.get_argument("org_id", None)
            # if org_id is not None:
            #     query = query.filter_by(organisation_id=org_id)

            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Function.title.ilike(r'%{}%'.format(term)))

            query = query.order_by(model.Function.title)
            query = self.paginate(query)

            for ob in query.all():
                son = to_dict(ob, include={'id', 'title'})
                son = simplify(son)
                son = normalise(son)
                sons.append(son)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    # test using curl
    # curl --cookie "_xsrf=2|d8b3038c|399eda1c903e9de19748e529c10603d3|1434072137" \
    # -H "X-Xsrftoken:2|d8b3038c|399eda1c903e9de19748e529c10603d3|1434072137" \
    # --data '{"title":"test1"}' http://192.168.59.103:8000/function.json
    # @handlers.authz('author')
    def post(self, function_id):
        '''
        Create a new function.
        '''
        if function_id != '':
            raise handlers.MethodError("Can't use POST for existing function.")

        log.info("request", self.request.body)
        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                function = model.Function()
                self._update(function, son)
                session.add(function)
                session.flush()
                session.expunge(function)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(function.id)

    # test using curl
    # curl --cookie "_xsrf=2|d8b3038c|399eda1c903e9de19748e529c10603d3|1434072137" \
    # -X PUT -H "X-Xsrftoken:2|d8b3038c|399eda1c903e9de19748e529c10603d3|1434072137" \
    # --data '{"title":"test2"}' http://192.168.59.103:8000/function/2f37de01-1833-41b6-9840-c5ed49d01772.json
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
