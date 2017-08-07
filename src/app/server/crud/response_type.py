from tornado.escape import json_encode
import tornado.web
import sqlalchemy
from sqlalchemy import func
import voluptuous.error

from activity import Activities
import base_handler
import errors
import logging
import model
from response_type import ResponseTypeError
from score import Calculator
from utils import ToSon, updater


log = logging.getLogger('app.crud.response_type')


class ResponseTypeHandler(base_handler.Paginate, base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self, response_type_id):
        '''Get single response type'''
        if not response_type_id:
            self.query()
            return

        program_id = self.get_argument('programId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            response_type, count = (
                session.query(model.ResponseType, func.count(model.Measure.id))
                .outerjoin(model.Measure)
                .filter(model.ResponseType.id == response_type_id)
                .filter(model.ResponseType.program_id == program_id)
                .group_by(model.ResponseType.id, model.ResponseType.program_id)
                .first()) or (None, None)
            if not response_type:
                raise errors.MissingDocError("No such response type")

            policy = user_session.policy.derive({
                'program': response_type.program,
                'surveygroups': response_type.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('response_type_view')

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
        program_id = self.get_argument('programId', '')
        term = self.get_argument('term', None)

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = (
                session.query(model.Program)
                .get(program_id))
            policy = user_session.policy.derive({
                'program': program,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('response_type_view')

            query = (
                session.query(model.ResponseType, func.count(model.Measure.id))
                .outerjoin(model.Measure)
                .filter(model.ResponseType.program_id == program_id)
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

    @tornado.web.authenticated
    def post(self, response_type_id):
        '''Create new'''
        if response_type_id:
            raise errors.ModelError("Can't specify ID when creating")

        program_id = self.get_argument('programId', '')

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
            policy.verify('response_type_add')

            rt_by_name = (
                session.query(model.ResponseType)
                .filter(model.ResponseType.program_id == program_id)
                .filter(model.ResponseType.name == self.request_son.name)
                .first())
            if rt_by_name:
                raise errors.ModelError(
                    "A response type of that name already exists")

            response_type = model.ResponseType(program=program)
            session.add(response_type)
            try:
                self._update(response_type, self.request_son)
            except ResponseTypeError as e:
                raise errors.ModelError(str(e))
            except voluptuous.error.Error as e:
                raise errors.ModelError(str(e))

            try:
                session.flush()
            except sqlalchemy.exc.IntegrityError as e:
                raise errors.ModelError.from_sa(e)

            response_type_id = str(response_type.id)
            # No need for survey update: RT is not being used yet

            act = Activities(session)
            act.record(user_session.user, response_type, ['create'])
            act.ensure_subscription(
                user_session.user, response_type, response_type.program,
                self.reason)
        self.get(response_type_id)

    @tornado.web.authenticated
    def delete(self, response_type_id):
        '''Delete'''

        program_id = self.get_argument('programId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            response_type = (
                session.query(model.ResponseType)
                .get((response_type_id, program_id)))
            if not response_type:
                raise errors.MissingDocError("No such response type")

            policy = user_session.policy.derive({
                'program': response_type.program,
                'surveygroups': response_type.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('response_type_del')

            session.delete(response_type)
            # No need for survey update: delete will fail if any measures are
            # using this RT

            act = Activities(session)
            act.record(user_session.user, response_type, ['delete'])
            act.ensure_subscription(
                user_session.user, response_type, response_type.program,
                self.reason)

        self.set_header("Content-Type", "text/plain")
        self.finish()

    @tornado.web.authenticated
    def put(self, response_type_id):
        '''Update existing'''

        program_id = self.get_argument('programId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            response_type = (
                session.query(model.ResponseType)
                .get((response_type_id, program_id)))
            if not response_type:
                raise errors.MissingDocError("No such response type")

            policy = user_session.policy.derive({
                'program': response_type.program,
                'surveygroups': response_type.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('response_type_edit')

            if 'name' in self.request_son:
                rt_by_name = (
                    session.query(model.ResponseType)
                    .filter(model.ResponseType.program_id == program_id)
                    .filter(model.ResponseType.name == self.request_son.name)
                    .first())
                if rt_by_name and rt_by_name != response_type:
                    raise errors.ModelError(
                        "A response type of that name already exists")

            try:
                self._update(response_type, self.request_son)
            except ResponseTypeError as e:
                raise errors.ModelError(str(e))
            except voluptuous.error.Error as e:
                raise errors.ModelError(str(e))

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
            act.record(user_session.user, response_type, verbs)
            act.ensure_subscription(
                user_session.user, response_type, response_type.program,
                self.reason)

        self.get(response_type_id)

    def _update(self, response_type, son):
        '''Apply user-provided data to the saved model.'''
        update = updater(response_type, error_factory=errors.ModelError)
        update('name', son)
        update('parts', son)
        update('formula', son)
