from tornado.escape import json_encode
import tornado.web
from sqlalchemy.orm import joinedload

from activity import Activities
import base_handler
import errors
import model
import logging
import voluptuous
from utils import ToSon, truthy, updater


log = logging.getLogger('app.crud.survey')


class SurveyHandler(base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self, survey_id):

        if not survey_id:
            self.query()
            return

        program_id = self.get_argument('programId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            survey = (
                session.query(model.Survey)
                .options(joinedload('program.surveygroups'))
                .get((survey_id, program_id)))
            if not survey:
                raise errors.MissingDocError("No such survey")

            policy = user_session.policy.derive({
                'survey': survey,
                'surveygroups': survey.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('survey_view')

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

        program_id = self.get_argument('programId', '')
        if not program_id:
            raise errors.ModelError("Program ID required")

        organisation_id = self.get_argument('organisationId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = (
                session.query(model.Program)
                .options(joinedload('surveygroups'))
                .get(program_id))

            policy = user_session.policy.derive({
                'program': program,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('program_view')

            query = (
                session.query(model.Survey)
                .filter(model.Survey.program_id == program_id)
                .order_by(model.Survey.title))

            deleted = self.get_argument('deleted', '')
            if deleted != '':
                deleted = truthy(deleted)
                query = query.filter(model.Survey.deleted == deleted)

            surveys = query.all()
            to_son = ToSon(
                r'/id$',
                r'/title$',
                r'/deleted$',
                r'/n_measures$',
                r'^/[0-9]+/error$',
                # Descend
                r'/[0-9]+$'
            )
            sons = to_son(surveys)

            # Add `purchased` metadata for nominated organisation
            if organisation_id:
                org = (
                    session.query(model.Organisation)
                    .get(organisation_id))
                policy = user_session.policy.derive({
                    'org': org,
                    'surveygroups': org.surveygroups,
                })
                policy.verify('surveygroup_interact')
                policy.verify('org_view')

                for son, survey in zip(sons, surveys):
                    son.purchased = survey in org.surveys

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @tornado.web.authenticated
    def post(self, survey_id):
        '''Create new.'''
        if survey_id:
            raise errors.MethodError("Can't use POST for existing object")

        program_id = self.get_argument('programId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = (
                session.query(model.Program)
                .options(joinedload('surveygroups'))
                .get(program_id))
            if not program:
                raise errors.ModelError("No such program")

            survey = model.Survey(program=program)
            self._update(survey, self.request_son)
            session.add(survey)

            # Need to flush so object has an ID to record action against.
            session.flush()

            policy = user_session.policy.derive({
                'program': program,
                'survey': survey,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('survey_add')

            act = Activities(session)
            act.record(user_session.user, survey, ['create'])
            act.ensure_subscription(
                user_session.user, survey, survey.program, self.reason)

            survey_id = str(survey.id)

        self.get(survey_id)

    @tornado.web.authenticated
    def put(self, survey_id):
        '''Update existing.'''
        if not survey_id:
            raise errors.MethodError("Survey ID required")

        program_id = self.get_argument('programId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            survey = (
                session.query(model.Survey)
                .options(joinedload('program'))
                .options(joinedload('program.surveygroups'))
                .get((survey_id, program_id)))
            if not survey:
                raise errors.MissingDocError("No such survey")
            self._update(survey, self.request_son)

            policy = user_session.policy.derive({
                'program': survey.program,
                'survey': survey,
                'surveygroups': survey.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('survey_edit')

            verbs = []
            if session.is_modified(survey):
                verbs.append('update')

            if survey.deleted:
                survey.deleted = False
                verbs.append('undelete')

            act = Activities(session)
            act.record(user_session.user, survey, verbs)
            act.ensure_subscription(
                user_session.user, survey, survey.program, self.reason)

        self.get(survey_id)

    @tornado.web.authenticated
    def delete(self, survey_id):
        if not survey_id:
            raise errors.MethodError("Survey ID required")

        program_id = self.get_argument('programId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            survey = (
                session.query(model.Survey)
                .options(joinedload('program'))
                .options(joinedload('program.surveygroups'))
                .get((survey_id, program_id)))
            if not survey:
                raise errors.MissingDocError("No such survey")

            policy = user_session.policy.derive({
                'program': survey.program,
                'survey': survey,
                'surveygroups': survey.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('survey_del')

            act = Activities(session)
            if not survey.deleted:
                act.record(user_session.user, survey, ['delete'])
            act.ensure_subscription(
                user_session.user, survey, survey.program, self.reason)

            survey.deleted = True

        self.finish()

    def _update(self, survey, son):
        update = updater(survey, error_factory=errors.ModelError)
        update('title', son)
        update('description', son, sanitise=True)
        try:
            update('structure', son)
        except voluptuous.Error as e:
            raise errors.ModelError("Structure is invalid: %s" % str(e))
