import datetime
import logging

from sqlalchemy.sql import func
from tornado.escape import json_decode, json_encode, url_escape, url_unescape
import tornado.options
import tornado.web

import base_handler
import errors
import model
from session import UserSession
import template
import theme


log = logging.getLogger('app.auth')


class LoginHandler(template.TemplateHandler):
    SESSION_LENGTH = datetime.timedelta(days=30)

    def prepare(self):
        self.session_expires = (
            datetime.datetime.utcnow() +
            type(self).SESSION_LENGTH)

    def get(self, user_id):
        '''
        Log in page (form).
        '''
        errormessage = self.get_argument("error", '')
        next_page = self.get_argument("next", "/")

        with model.session_scope() as session:
            params = template.TemplateParams(session)
            theme_params = theme.ThemeParams(session)
            self.render(
                "../client/templates/login.html",
                params=params, theme=theme_params, next=next_page,
                error=errormessage)

    def post(self, user_id):
        '''
        Method for user to provide credentials and log in.
        '''
        email = self.get_argument("email", "")
        password = self.get_argument("password", "")

        with model.session_scope() as session:
            user = (
                session.query(model.AppUser)
                .filter(func.lower(model.AppUser.email) == func.lower(email))
                .first())

            if not user or user.password != password:
                self.clear_cookie("user")
                self.clear_cookie("superuser")
                error_msg = "?error={}".format(
                    tornado.escape.url_escape("Login incorrect"))
                self.redirect("/login/" + error_msg)
                return

            if user.deleted or user.organisation.deleted:
                self.clear_cookie("user")
                self.clear_cookie("superuser")
                error_msg = "?error=" + tornado.escape.url_escape(
                    "Your account is inactive")
                self.redirect("/login/" + error_msg)
                return

            self.set_secure_cookie(
                "user", str(user.id).encode('utf8'),
                expires=self.session_expires)

            user_session = UserSession(user, None)
            if user_session.policy.check('admin'):
                self.set_secure_cookie(
                    "superuser", str(user.id).encode('utf8'),
                    expires=self.session_expires)

        # Make sure the XSRF token expires at the same time
        self.xsrf_token

        self.redirect('/' + self.get_argument("next", "#/2/"))

    @property
    def xsrf_token(self):
        # Workaround for XSRF cookie that expires too soon: because
        # _current_user is not defined yet, the default implementation of
        # xsrf_token does not set the cookie's expiration. The mismatch
        # between the _xsrf and user cookie expiration causes POST requests
        # to fail even when the user thinks they are still logged in.
        token = super().xsrf_token
        self.set_cookie('_xsrf', token, expires=self.session_expires)
        return token

    @tornado.web.authenticated
    def put(self, user_id):
        '''
        Allows an admin to impersonate any other user without needing to know
        their password.
        '''
        superuser_id = self.get_secure_cookie('superuser')

        if not superuser_id:
            raise errors.AuthzError(
                "Not authorised: you are not an administrator")
        superuser_id = superuser_id.decode('utf8')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            user = session.query(model.AppUser).get(user_id)
            if not user:
                raise errors.MissingDocError("No such user")

            policy = user_session.policy.derive({
                'user': user,
                'surveygroups': user.surveygroups,
            })
            policy.verify('user_impersonate')

            self._store_last_user(session)

            name = user.name
            log.warn(
                'User %s is impersonating %s',
                policy.context.s.user.email, user.email)
            self.set_secure_cookie(
                "user", str(user.id).encode('utf8'),
                expires=self.session_expires)

            # Make sure the XSRF token expires at the same time
            self.xsrf_token

        self.set_header("Content-Type", "text/plain")
        self.write("Impersonating %s" % name)
        self.finish()

    def _store_last_user(self, session):
        user_id = self.get_secure_cookie('user')
        if user_id is None:
            return
        user_id = user_id.decode('utf8')

        try:
            past_users = self.get_cookie('past-users')
            past_users = json_decode(url_unescape(past_users, plus=False))
            log.warn('Past users: %s', past_users)
        except Exception as e:
            log.warn('Failed to decode past users: %s', e)
            past_users = []

        if not user_id:
            return
        try:
            past_users = list(filter(lambda x: x['id'] != user_id, past_users))
        except KeyError:
            past_users = []

        log.warn('%s', user_id)
        user = session.query(model.AppUser).get(user_id)
        if not user:
            return

        past_users.insert(0, {'id': user_id, 'name': user.name})
        past_users = past_users[:10]
        log.warn('%s', past_users)
        self.set_cookie('past-users', url_escape(
            json_encode(past_users), plus=False))


class LogoutHandler(base_handler.BaseHandler):
    def get(self):
        self.clear_cookie("user")
        self.clear_cookie("superuser")
        self.redirect(self.get_argument("next", "/"))
