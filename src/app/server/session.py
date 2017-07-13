from sqlalchemy.orm import joinedload
from sqlalchemy.orm.session import object_session

import authz
import config
import errors
import model


class UserSession:
    def __init__(self, db_session, user_id, superuser_id):
        self.db_session = db_session
        self.user = self.get_user(user_id, superuser_id)
        self.policy = self.get_policy()

    @property
    def org(self):
        if self.user:
            return self.user.organisation
        else:
            return None

    def get_user(self, user_id, superuser_id):
        user = (
            self.db_session.query(model.AppUser)
            .options(joinedload('organisation'))
            .get(user_id))
        if not user:
            return None
        if user.deleted and not superuser_id:
            return None
        return user

    def get_policy(self):
        rule_declarations = config.get_resource('authz')
        policy = authz.Policy(error_factory=errors.AuthzError, aspect='server')
        for decl in rule_declarations:
            policy.declare(decl)

        policy.context.update({'s': self})
        return policy

    def has_role(self, *names):
        return model.has_privillege(self.user.role, *names)

    def purchased_survey(self, survey):
        session = object_session(survey)
        count = (
            session.query(model.PurchasedSurvey)
            .filter(model.PurchasedSurvey.program_id == survey.program_id)
            .filter(model.PurchasedSurvey.survey_id == survey.id)
            .filter(model.PurchasedSurvey.organisation_id == self.org.id)
            .count())
        return count > 0

    def purchased_program(self, program):
        session = object_session(program)
        count = (
            session.query(model.PurchasedSurvey)
            .filter(model.PurchasedSurvey.program_id == program.id)
            .filter(model.PurchasedSurvey.organisation_id == self.org.id)
            .count())
        return count > 0
