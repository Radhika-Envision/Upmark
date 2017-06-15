from concurrent.futures import ThreadPoolExecutor
import datetime
import logging
import time
import uuid

from tornado import gen
from tornado.concurrent import run_on_executor
from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.sql import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.session import make_transient

from activity import Activities
import handlers
import model
from score import Calculator
from utils import ToSon, truthy, updater


log = logging.getLogger('app.crud.program')

MAX_WORKERS = 4


class ProgramCentric:
    '''
    Mixin for handlers that deal with models that have a program ID as part of
    a composite primary key.
    '''
    @property
    def program_id(self):
        program_id = self.get_argument("programId", "")
        if program_id == '':
            raise handlers.MethodError("Program ID is required")

        return program_id

    @property
    def program(self):
        if not hasattr(self, '_program'):
            with model.session_scope() as session:
                program = session.query(model.Program).get(self.program_id)
                if program is None:
                    raise handlers.MissingDocError("No such program")
                session.expunge(program)
            self._program = program
        return self._program

    def check_editable(self):
        if not self.program.is_editable:
            raise handlers.MethodError("This program is closed for editing")


class ProgramHandler(handlers.Paginate, handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    def get(self, program_id):
        '''
        Get a single program.
        '''
        if program_id == "":
            self.query()
            return

        with model.session_scope() as session:
            try:
                query = session.query(model.Program)
                program = query.get(program_id)
                if program is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such program")

            to_son = ToSon(
                r'/ob_type$',
                r'/id$',
                r'/tracking_id$',
                r'/title$',
                r'</description$',
                r'/created$',
                r'/deleted$',
                r'/is_editable$',
                r'^/error$',
                r'/has_quality$',
                r'/hide_aggregate$',
            )
            if not self.has_privillege('author'):
                to_son.exclude(
                    r'/response_types.*score$',
                    r'/response_types.*formula$',
                )
            son = to_son(program)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self):
        '''
        Get a list of programs.
        '''

        term = self.get_argument('term', '')
        is_editable = truthy(self.get_argument('editable', ''))

        sons = []
        with model.session_scope() as session:
            query = session.query(model.Program)
            if term != '':
                query = query.filter(
                    model.Program.title.ilike(r'%{}%'.format(term)))

            if is_editable:
                query = query.filter(model.Program.finalised_date==None)

            deleted = self.get_argument('deleted', '')
            if deleted != '':
                deleted = truthy(deleted)
                query = query.filter(model.Program.deleted == deleted)

            query = query.order_by(model.Program.created.desc())
            query = self.paginate(query)

            to_son = ToSon(
                r'/id$',
                r'/title$',
                r'</description$',
                r'/deleted$',
                r'^/[0-9]+/error$',
                r'/[0-9]+$'
            )
            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('author')
    @gen.coroutine
    def post(self, program_id):
        '''
        Create a new program.
        '''
        if program_id != '':
            raise handlers.MethodError("Can't use POST for existing program.")

        duplicate_id = self.get_argument('duplicateId', '')

        with model.session_scope() as session:
            program = model.Program()
            self._update(program, self.request_son)
            session.add(program)

            # Need to flush so object has an ID to record action against.
            session.flush()
            program_id = str(program.id)

            act = Activities(session)

            if duplicate_id != '':
                source_program = (session.query(model.Program)
                    .get(duplicate_id))
                if source_program is None:
                    raise handlers.MissingDocError(
                        "Source program does not exist")
                yield self.duplicate_structure(
                    source_program, program, session)
                source_program.finalised_date = datetime.datetime.utcnow()
                act.record(self.current_user, source_program, ['state'])

            act.record(self.current_user, program, ['create'])
            if not act.has_subscription(self.current_user, program):
                act.subscribe(self.current_user, program)
                self.reason("Subscribed to program")

        self.get(program_id)

    @run_on_executor
    def duplicate_structure(self, source_program, target_program, session):
        '''
        Duplicate an existing program - just the structure (e.g. survey,
        qnodes and measures).
        '''
        log.debug('Duplicating %s from %s', target_program, source_program)

        target_program.tracking_id = source_program.tracking_id

        def dissociate(entity):
            # Expunge followed by make_transient tells SQLAlchemy to use INSERT
            # instead of UPDATE, thus duplicating the row in the table.
            session.expunge(entity)
            make_transient(entity)
            session.add(entity)
            return entity

        def dup_surveys(surveys):
            for survey in surveys:
                if survey.deleted:
                    continue
                log.debug('Duplicating %s', survey)
                qs = survey.qnodes
                dissociate(survey)
                survey.program_id = target_program.id
                dup_qnodes(qs)

        def dup_qnodes(qnodes):
            for qnode in qnodes:
                if qnode.deleted:
                    continue
                log.debug('Duplicating %s', qnode)
                children = qnode.children
                qnode_measures = qnode.qnode_measures
                dissociate(qnode)
                qnode.program_id = target_program.id
                dup_qnodes(children)
                dup_qnode_measures(qnode_measures)

        # Measures are shared, so we keep track of which ones have already been
        # duplicated.
        processed_measure_ids = set()
        processed_response_type_ids = set()

        def dup_qnode_measures(qnode_measures):
            for qnode_measure in qnode_measures:
                log.debug('Duplicating %s', qnode_measure)
                if qnode_measure.measure_id not in processed_measure_ids:
                    dup_measure(qnode_measure.measure)
                for measure_variable in qnode_measure.source_vars:
                    dup_variable(measure_variable)
                dissociate(qnode_measure)
                qnode_measure.program_id = target_program.id

        def dup_variable(measure_variable):
            log.debug('Duplicating %s', measure_variable)
            if measure_variable.source_measure_id not in processed_measure_ids:
                dup_measure(measure_variable.source_qnode_measure.measure)
            if measure_variable.target_measure_id not in processed_measure_ids:
                dup_measure(measure_variable.target_qnode_measure.measure)
            dissociate(measure_variable)
            measure_variable.program_id = target_program.id
            session.add(measure_variable)

        def dup_measure(measure):
            log.debug('Duplicating %s', measure)
            if measure.response_type_id not in processed_response_type_ids:
                dup_response_type(measure.response_type)
            dissociate(measure)
            measure.program_id = target_program.id
            processed_measure_ids.add(measure.id)

        def dup_response_type(response_type):
            log.debug('Duplicating %s', response_type)
            dissociate(response_type)
            response_type.program_id = target_program.id
            processed_response_type_ids.add(response_type.id)

        dup_surveys(source_program.surveys)

    @handlers.authz('author')
    def delete(self, program_id):
        '''
        Delete an existing program.
        '''
        if program_id == '':
            raise handlers.MethodError("Program ID required")

        try:
            with model.session_scope() as session:
                program = session.query(model.Program)\
                    .get(program_id)
                if program is None:
                    raise ValueError("No such object")
                if not program.is_editable:
                    raise handlers.MethodError(
                        "This program is closed for editing")

                act = Activities(session)
                if not program.deleted:
                    act.record(self.current_user, program, ['delete'])
                if not act.has_subscription(self.current_user, program):
                    act.subscribe(self.current_user, program)
                    self.reason("Subscribed to program")

                program.deleted = True
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError("Program is in use")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such program")

        self.finish()

    @handlers.authz('author')
    def put(self, program_id):
        '''
        Update an existing program.
        '''
        if program_id == '':
            raise handlers.MethodError(
                "Can't use PUT for new program (no ID).")

        editable = self.get_argument('editable', '')
        if editable != '':
            self._update_state(program_id, editable)
            return

        try:
            with model.session_scope() as session:
                program = session.query(model.Program).get(program_id)
                if program is None:
                    raise ValueError("No such object")

                if not program.is_editable:
                    raise handlers.MethodError(
                        "This program is closed for editing")

                calculator = Calculator.structural()
                if self.request_son['has_quality'] != program.has_quality:
                    # Recalculate stats for surveys. This will trigger the
                    # recalculation of the submissions in the recalculation
                    # daemon.
                    for survey in program.surveys:
                        calculator.mark_survey_dirty(survey)

                self._update(program, self.request_son)

                calculator.execute()

                verbs = []
                if session.is_modified(program):
                    verbs.append('update')

                if program.deleted:
                    program.deleted = False
                    verbs.append('undelete')

                act = Activities(session)
                act.record(self.current_user, program, verbs)
                if not act.has_subscription(self.current_user, program):
                    act.subscribe(self.current_user, program)
                    self.reason("Subscribed to program")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such program")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(program_id)

    def _update_state(self, program_id, editable):
        '''
        Just update the state of the program (not title etc.)
        '''
        try:
            with model.session_scope() as session:
                program = session.query(model.Program).get(program_id)
                if program is None:
                    raise ValueError("No such object")

                if editable != '':
                    if truthy(editable):
                        program.finalised_date = None
                    else:
                        program.finalised_date = datetime.datetime.utcnow()

                act = Activities(session)
                if session.is_modified(program):
                    act.record(self.current_user, program, ['state'])
                if not act.has_subscription(self.current_user, program):
                    act.subscribe(self.current_user, program)
                    self.reason("Subscribed to program")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such program")
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(program_id)

    def _update(self, program, son):
        '''
        Apply program-provided data to the saved model.
        '''
        update = updater(program, error_factory=handlers.ModelError)
        update('title', son)
        update('description', son, sanitise=True)
        update('has_quality', son)
        update('hide_aggregate', son)


class ProgramTrackingHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, program_id):
        '''
        Get a list of programs that share the same lineage.
        '''
        if program_id == '':
            raise handlers.MethodError("Program ID is required")

        with model.session_scope() as session:
            program = session.query(model.Program).get(program_id)
            if program is None:
                raise handlers.MissingDocError("No such program")

            query = (session.query(model.Program)
                .filter(model.Program.tracking_id == program.tracking_id)
                .order_by(model.Program.created))

            deleted = self.get_argument('deleted', '')
            if deleted != '':
                deleted = truthy(deleted)
                query = query.filter(model.Program.deleted == deleted)

            to_son = ToSon(
                r'/id$',
                r'/title$',
                r'/is_editable$',
                r'/deleted$',
                # Descend
                r'/[0-9]+$',
            )
            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()


class ProgramHistoryHandler(handlers.BaseHandler):
    def initialize(self, mapper):
        self.mapper = mapper

    @tornado.web.authenticated
    def get(self, entity_id):
        '''
        Get a list of programs that some entity belongs to. For example,
        a single survey may be present in multiple programs.
        '''
        with model.session_scope() as session:
            query = (session.query(model.Program)
                .join(self.mapper)
                .filter(self.mapper.id == entity_id)
                .order_by(model.Program.created))

            deleted = self.get_argument('deleted', '')
            if deleted != '':
                deleted = truthy(deleted)
                query = query.filter(model.Program.deleted == deleted)

            to_son = ToSon(
                r'/id$',
                r'/title$',
                r'/is_editable$',
                r'/created$',
                r'/deleted$',
                # Descend
                r'/[0-9]+$',
            )
            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()
