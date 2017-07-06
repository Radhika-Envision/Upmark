from munch import DefaultMunch
from sqlalchemy.orm import joinedload

import authz
import config
import errors
import model
from undefined import undefined


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
        policy = authz.Policy(error_factory=errors.AuthzError)
        for decl in rule_declarations:
            policy.declare(decl)

        policy.context.update({
            's': DefaultMunch(
                undefined,
                has_role=self.has_role,
                user=self.user,
                org=self.org,
                purchased_survey=self.purchased_survey,
            ),
        })
        return policy

    def has_role(self, *names):
        return model.has_privillege(self.user.role, *names)

    def purchased_survey(self, survey):
        return survey in self.org.surveys
