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

class MeasureHandler(handlers.Paginate, handlers.BaseHandler):
    @tornado.web.authenticated
    def get(self, measure_id):
        '''
        Get a single measure.
        '''
        if measure_id == "":
            self.query()
            return

        with model.session_scope() as session:
            try:
                measure = session.query(model.Measure).get(measure_id)
                if measure is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such measure")

            son = to_dict(measure, include={'id', 'title', 'intent', 'inputs', 'scenario', 'questions'})
            son = simplify(son)
            son = normalise(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self):
        '''
        Get a list of users.
        '''

        sons = []
        with model.session_scope() as session:
            query = session.query(model.Measure)
            query = query.order_by(model.Measure.seq)
            query = self.paginate(query)

            for ob in query.all():
                son = to_dict(ob, include={'id', 'title', 'intent', 'inputs', 'scenario', 'questions'})
                son = simplify(son)
                son = normalise(son)
                # son["category"] = org
                sons.append(son)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('author')
    def post(self, measure_id):
        '''
        Create a new user.
        '''
        if measure_id != '':
            raise handlers.MethodError("Can't use POST for existing measure.")

        subprocess_id = self.get_argument('subprocess_id', None)
        if subprocess_id == None:
            raise handlers.MethodError("Can't use POST measure without subprocess_id.")

        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                measure = model.Measure()
                self._update(measure, son)
                branch = self.get_current_branch()
                measure.branch = branch
                measure.subprocess_id = subprocess_id
                session.add(measure)
                session.flush()
                session.expunge(measure)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.finish(str(measure.id))

    @handlers.authz('author')
    def put(self, measure_id):
        '''
        Update an existing user.
        '''
        if measure_id == '':
            raise handlers.MethodError("Can't use PUT for new measure (no ID).")
        son = json_decode(self.request.body)

        try:
            with model.session_scope() as session:
                measure = session.query(model.Measure).get(measure_id)
                if measure is None:
                    raise ValueError("No such object")
                self._update(measure, son)
                session.add(measure)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such measure")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(measure_id)

    def _update(self, measure, son):
        '''
        Apply user-provided data to the saved model.
        '''
        if son.get('seq', '') != '':
            measure.seq = son['seq']
        if son.get('title', '') != '':
            measure.title = son['title']
        if son.get('weight', '') != '':
            measure.weight = son['weight']
        if son.get('intent', '') != '':
            measure.intent = son['intent']
        if son.get('inputs', '') != '':
            measure.inputs = son['inputs']
        if son.get('scenario', '') != '':
            measure.scenario = son['scenario']
        if son.get('questions', '') != '':
            measure.questions = son['questions']
        if son.get('response_type', '') != '':
            measure.response_type = son['response_type']
        if son.get('branch', '') != '':
            measure.branch = son['branch']

    # TODO : we can save branch code somewhere global area 
    def get_current_branch(self):
        with model.session_scope() as session:
            survey = session.query(model.Survey).order_by(sqlalchemy.desc(model.Survey.created)).one()
            return survey.branch
