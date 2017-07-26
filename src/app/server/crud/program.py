from concurrent.futures import ThreadPoolExecutor
import datetime
import logging

from tornado import gen
from tornado.concurrent import run_on_executor
from tornado.escape import json_encode
import tornado.web
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.session import make_transient

from activity import Activities
import base_handler
import errors
import model
from score import Calculator
from utils import ToSon, truthy, updater
from .surveygroup import assign_surveygroups, filter_surveygroups


log = logging.getLogger('app.crud.program')

MAX_WORKERS = 4


class ProgramHandler(base_handler.Paginate, base_handler.BaseHandler):
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
            user_session = self.get_user_session(session)

            program = (
                session.query(model.Program)
                .options(joinedload('surveygroups'))
                .get(program_id))
            if not program:
                raise errors.MissingDocError("No such program")

            policy = user_session.policy.derive({
                'program': program,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('program_view')

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
                r'/[0-9+]$',
            )
            if policy.check('surveygroup_browse'):
                to_son.add(r'^/surveygroups$')
            if not policy.check('author'):
                to_son.exclude(
                    r'/response_types.*score$',
                    r'/response_types.*formula$',
                )
            son = to_son(program)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        '''
        Get a list of programs.
        '''

        term = self.get_argument('term', '')
        is_editable = truthy(self.get_argument('editable', ''))

        sons = []
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            query = session.query(model.Program)

            policy = user_session.policy.derive({})
            if not policy.check('surveygroup_interact_all'):
                query = filter_surveygroups(
                    session, query, user_session.user.id,
                    [], [model.program_surveygroup])

            if term != '':
                query = query.filter(
                    model.Program.title.ilike(r'%{}%'.format(term)))

            if is_editable:
                query = query.filter(model.Program.finalised_date == None)

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

    @tornado.web.authenticated
    @gen.coroutine
    def post(self, program_id):
        '''
        Create a new program.
        '''
        if program_id:
            raise errors.MethodError("Can't use POST for existing program.")

        duplicate_id = self.get_argument('duplicateId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = model.Program()
            self._update(program, self.request_son)
            session.add(program)

            try:
                assign_surveygroups(user_session, program, self.request_son)
            except ValueError as e:
                raise errors.ModelError(str(e))

            policy = user_session.policy.derive({
                'program': program,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('program_add')

            # Need to flush so object has an ID to record action against.
            session.flush()

            act = Activities(session)

            if duplicate_id:
                source_program = (
                    session.query(model.Program)
                    .get(duplicate_id))
                if not source_program:
                    raise errors.MissingDocError(
                        "Source program does not exist")

                policy = user_session.policy.derive({
                    'program': source_program,
                    'surveygroups': source_program.surveygroups,
                })
                policy.verify('surveygroup_interact')
                policy.verify('program_view')

                yield self.duplicate_structure(
                    source_program, program, session)
                source_program.finalised_date = datetime.datetime.utcnow()
                act.record(user_session.user, source_program, ['state'])

            act.record(user_session.user, program, ['create'])
            if not act.has_subscription(user_session.user, program):
                act.subscribe(user_session.user, program)
                self.reason("Subscribed to program")

            program_id = program.id

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

    @tornado.web.authenticated
    def delete(self, program_id):
        '''
        Delete an existing program.
        '''
        if not program_id:
            raise errors.MethodError("Program ID required")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = session.query(model.Program).get(program_id)
            if not program:
                raise errors.MissingDocError("No such program")

            policy = user_session.policy.derive({
                'program': program,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('program_del')

            act = Activities(session)
            if not program.deleted:
                act.record(user_session.user, program, ['delete'])
            if not act.has_subscription(user_session.user, program):
                act.subscribe(user_session.user, program)
                self.reason("Subscribed to program")

            program.deleted = True

        self.finish()

    @tornado.web.authenticated
    def put(self, program_id):
        '''
        Update an existing program.
        '''
        if program_id == '':
            raise errors.MethodError(
                "Can't use PUT for new program (no ID).")

        editable = self.get_argument('editable', '')
        if editable != '':
            self._update_state(program_id, truthy(editable))
            return

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = session.query(model.Program).get(program_id)
            if not program:
                raise errors.MissingDocError("No such program")

            try:
                groups_changed = assign_surveygroups(
                    user_session, program, self.request_son)
            except ValueError as e:
                raise errors.ModelError(str(e))

            policy = user_session.policy.derive({
                'program': program,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('program_edit')

            if not program.is_editable:
                raise errors.MethodError("This program is closed for editing")

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
            if session.is_modified(program) or groups_changed:
                verbs.append('update')

            if program.deleted:
                program.deleted = False
                verbs.append('undelete')

            act = Activities(session)
            act.record(user_session.user, program, verbs)
            if not act.has_subscription(user_session.user, program):
                act.subscribe(user_session.user, program)
                self.reason("Subscribed to program")
        self.get(program_id)

    def _update_state(self, program_id, editable):
        '''
        Just update the state of the program (not title etc.)
        '''
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = session.query(model.Program).get(program_id)
            if not program:
                raise errors.MissingDocError("No such program")

            policy = user_session.policy.derive({
                'program': program,
            })

            if editable:
                program.finalised_date = None
                policy.verify('program_edit')
            else:
                policy.verify('program_edit')
                program.finalised_date = datetime.datetime.utcnow()

            act = Activities(session)
            if session.is_modified(program):
                act.record(user_session.user, program, ['state'])
            if not act.has_subscription(user_session.user, program):
                act.subscribe(user_session.user, program)
                self.reason("Subscribed to program")
        self.get(program_id)

    def _update(self, program, son):
        '''
        Apply program-provided data to the saved model.
        '''
        update = updater(program, error_factory=errors.ModelError)
        update('title', son)
        update('description', son, sanitise=True)
        update('has_quality', son)
        update('hide_aggregate', son)


class ProgramTrackingHandler(base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self, program_id):
        '''
        Get a list of programs that share the same lineage.
        '''
        if program_id == '':
            raise errors.MethodError("Program ID is required")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = session.query(model.Program).get(program_id)
            if not program:
                raise errors.MissingDocError("No such program")

            policy = user_session.policy.derive({
                'program': program,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('program_view')

            query = (
                session.query(model.Program)
                .filter(model.Program.tracking_id == program.tracking_id)
                .order_by(model.Program.created))

            if not policy.check('surveygroup_interact_all'):
                query = filter_surveygroups(
                    session, query, user_session.user.id,
                    [], [model.program_surveygroup])

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


class ProgramHistoryHandler(base_handler.BaseHandler):
    def initialize(self, mapper):
        self.mapper = mapper

    @tornado.web.authenticated
    def get(self, entity_id):
        '''
        Get a list of programs that some entity belongs to. For example,
        a single survey may be present in multiple programs.
        '''
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            query = (
                session.query(model.Program)
                .join(self.mapper)
                .filter(self.mapper.id == entity_id)
                .order_by(model.Program.created))

            policy = user_session.policy.derive({})
            if not policy.check('surveygroup_interact_all'):
                query = filter_surveygroups(
                    session, query, user_session.user.id,
                    [], [model.program_surveygroup])

            deleted = self.get_argument('deleted', '')
            if deleted != '':
                deleted = truthy(deleted)
                query = query.filter(model.Program.deleted == deleted)

            programs = [
                program for program in query.all()
                if user_session.policy.derive({'program': program}).check()]

            to_son = ToSon(
                r'/id$',
                r'/title$',
                r'/is_editable$',
                r'/created$',
                r'/deleted$',
                # Descend
                r'/[0-9]+$',
            )
            sons = to_son(programs)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()
