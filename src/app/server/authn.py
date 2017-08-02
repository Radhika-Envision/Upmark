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


class SessionMixin:
    SESSION_LENGTH = datetime.timedelta(days=30)

    def prepare(self):
        self.session_expires = (
            datetime.datetime.utcnow() +
            type(self).SESSION_LENGTH)

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


class LoginHandler(SessionMixin, template.TemplateHandler):

    def get(self):
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

    def post(self):
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

            user_cookie = "user={}".format(user.id)

            user_session = UserSession(user, None)
            if user_session.policy.check('user_try_impersonate'):
                user_cookie = self.set_superuser(user_cookie, user)
            else:
                self.clear_cookie("superuser")

            self.set_secure_cookie(
                "user", user_cookie.encode('utf8'),
                expires=self.session_expires)

        # Make sure the XSRF token expires at the same time
        self.xsrf_token

        self.redirect('/' + self.get_argument("next", "#/2/"))

    def set_superuser(self, cookie, user):
        # Store both user and superuser ("true user") IDs in a single
        # secure cookie. This is more secure than using two separate
        # cookies: it prevents a superuser from continuing to impersonate
        # another user after the superuser's own account has been
        # deactivated.
        # Also store a flag in a separate cookie just to let the client know
        # that the user is a superuser - because it's hard to decode the
        # `user` cookie.
        self.set_cookie(
            "superuser", 'yes'.encode('utf8'),
            expires=self.session_expires)
        return cookie + ", superuser={}".format(user.id)


class ImpersonateHandler(SessionMixin, base_handler.BaseHandler):

    @tornado.web.authenticated
    def put(self, user_id):
        '''
        Allows an admin to impersonate any other user without needing to know
        their password.
        '''
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            user = session.query(model.AppUser).get(user_id)
            if not user:
                raise errors.MissingDocError("No such user")
            if user.deleted:
                raise errors.ModelError("That user has been deactivated")

            policy = user_session.policy.derive({
                'user': user,
                'surveygroups': user.surveygroups,
            })
            policy.verify('user_impersonate')

            self.store_last_user(session, user_session.user.id)

            name = user.name
            log.warning(
                'User %s is impersonating %s',
                user_session.superuser.email, user.email)

            user_ids = "user={}, superuser={}".format(
                user.id, user_session.superuser.id)
            self.set_secure_cookie(
                "user", user_ids.encode('utf8'),
                expires=self.session_expires)

            # Make sure the XSRF token expires at the same time
            self.xsrf_token

        self.set_header("Content-Type", "text/plain")
        self.write("Impersonating %s" % name)
        self.finish()

    def store_last_user(self, session, user_id):
        user_id = str(user_id)

        past_users = self.get_cookie('past-users')
        if not past_users:
            past_users = []
        else:
            try:
                past_users = json_decode(url_unescape(past_users, plus=False))
                log.warning('Past users: %s', past_users)
            except Exception as e:
                log.warning('Failed to decode past users: %s', e)
                past_users = []

        try:
            past_users = list(filter(lambda x: x['id'] != user_id, past_users))
        except KeyError:
            past_users = []

        user = session.query(model.AppUser).get(user_id)
        if not user:
            return

        past_users.insert(0, {'id': user_id, 'name': user.name})
        past_users = past_users[:10]
        log.debug('%s', past_users)
        self.set_cookie('past-users', url_escape(
            json_encode(past_users), plus=False))


class LogoutHandler(base_handler.BaseHandler):
    def get(self):
        self.clear_cookie("user")
        self.clear_cookie("superuser")
        self.redirect(self.get_argument("next", "/"))
