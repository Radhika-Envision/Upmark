from tornado.escape import json_encode
import tornado.web
import sqlalchemy

from activity import Activities
import auth
import base_handler
import crud.program
import errors
import model
import logging
import voluptuous
from utils import ToSon, truthy, updater


log = logging.getLogger('app.crud.survey')


class SurveyHandler(crud.program.ProgramCentric, base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self, survey_id):

        if survey_id == '':
            self.query()
            return

        with model.session_scope() as session:
            try:
                survey = session.query(model.Survey)\
                    .get((survey_id, self.program_id))

                if survey is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise errors.MissingDocError("No such survey")

            self.check_browse_program(session, self.program_id, survey_id)

            to_son = ToSon(
                # Any
                r'/ob_type$',
                r'/id$',
                r'/title$',
                r'/seq$',
                r'/created$',
                r'/deleted$',
                r'/is_editable$',
                r'/n_measures$',
                r'^/error$',
                r'/program/tracking_id$',
                # Root-only
                r'<^/description$',
                r'^/structure.*',
                # Nested
                r'/program$',
            )
            son = to_son(survey)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def query(self):
        '''Get a list.'''
        with model.session_scope() as session:
            query = session.query(model.Survey)\
                .filter_by(program_id=self.program_id)\
                .order_by(model.Survey.title)

            deleted = self.get_argument('deleted', '')
            if deleted != '':
                deleted = truthy(deleted)
                query = query.filter(model.Survey.deleted == deleted)

            to_son = ToSon(
                r'/id$',
                r'/title$',
                r'/deleted$',
                r'/n_measures$',
                r'^/[0-9]+/error$',
                # Descend
                r'/[0-9]+$'
            )
            sons = to_son(query.all())

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @auth.authz('author')
    def post(self, survey_id):
        '''Create new.'''
        if survey_id != '':
            raise errors.MethodError("Can't use POST for existing object")

        self.check_editable()

        try:
            with model.session_scope() as session:
                survey = model.Survey(program_id=self.program_id)
                self._update(survey, self.request_son)
                session.add(survey)

                # Need to flush so object has an ID to record action against.
                session.flush()

                act = Activities(session)
                act.record(self.current_user, survey, ['create'])
                if not act.has_subscription(self.current_user, survey):
                    act.subscribe(self.current_user, survey.program)
                    self.reason("Subscribed to program")

                survey_id = str(survey.id)
        except sqlalchemy.exc.IntegrityError as e:
            raise errors.ModelError.from_sa(e)
        self.get(survey_id)

    @auth.authz('author')
    def put(self, survey_id):
        '''Update existing.'''
        if survey_id == '':
            raise errors.MethodError("Survey ID required")

        self.check_editable()

        try:
            with model.session_scope() as session:
                survey = session.query(model.Survey)\
                    .get((survey_id, self.program_id))
                if survey is None:
                    raise ValueError("No such object")
                self._update(survey, self.request_son)

                verbs = []
                if session.is_modified(survey):
                    verbs.append('update')

                if survey.deleted:
                    survey.deleted = False
                    verbs.append('undelete')

                act = Activities(session)
                act.record(self.current_user, survey, verbs)
                if not act.has_subscription(self.current_user, survey):
                    act.subscribe(self.current_user, survey.program)
                    self.reason("Subscribed to program")

        except (sqlalchemy.exc.StatementError, ValueError):
            raise errors.MissingDocError("No such survey")
        except sqlalchemy.exc.IntegrityError as e:
            raise errors.ModelError.from_sa(e)
        self.get(survey_id)

    @auth.authz('author')
    def delete(self, survey_id):
        if survey_id == '':
            raise errors.MethodError("Survey ID required")

        self.check_editable()

        try:
            with model.session_scope() as session:
                survey = session.query(model.Survey)\
                    .get((survey_id, self.program_id))
                if survey is None:
                    raise ValueError("No such object")

                act = Activities(session)
                if not survey.deleted:
                    act.record(self.current_user, survey, ['delete'])
                if not act.has_subscription(self.current_user, survey):
                    act.subscribe(self.current_user, survey.program)
                    self.reason("Subscribed to program")

                survey.deleted = True

        except sqlalchemy.exc.IntegrityError as e:
            raise errors.ModelError("This survey is in use")
        except (sqlalchemy.exc.StatementError, ValueError):
            raise errors.MissingDocError("No such survey")

        self.finish()

    def _update(self, survey, son):
        update = updater(survey, error_factory=errors.ModelError)
        update('title', son)
        update('description', son, sanitise=True)
        try:
            update('structure', son)
        except voluptuous.Error as e:
            raise errors.ModelError("Structure is invalid: %s" % str(e))
