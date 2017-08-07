from sqlalchemy.orm.session import object_session

import authz
import config
import errors
import model


class UserSession:
    def __init__(self, user, superuser):
        self.user = user
        self.org = user.organisation
        self.superuser = superuser
        self.policy = self.create_policy()

    def create_policy(self):
        rule_declarations = config.get_resource('authz')
        policy = authz.Policy(error_factory=errors.AuthzError, aspect='server')
        for decl in rule_declarations:
            policy.declare(decl)

        policy.context.update({'s': self})
        return policy

    def member_of_any(self, surveygroups):
        surveygroups = {
            sg for sg in surveygroups
            if not sg.deleted}
        return not self.user.surveygroups.isdisjoint(surveygroups)

    def super_is_member_of_any(self, surveygroups):
        surveygroups = {
            sg for sg in surveygroups
            if not sg.deleted}
        return not self.superuser.surveygroups.isdisjoint(surveygroups)

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
