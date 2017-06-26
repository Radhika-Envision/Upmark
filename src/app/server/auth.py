import datetime
import functools
import logging

import sqlalchemy
from sqlalchemy.sql import func
from tornado.escape import json_decode, json_encode, url_escape, url_unescape
import tornado.options
import tornado.web

import base_handler
import errors
import model
import template
import theme


log = logging.getLogger('app.auth')


class AuthLoginHandler(template.TemplateHandler):
    SESSION_LENGTH = datetime.timedelta(days=30)

    def prepare(self):
        self.session_expires = datetime.datetime.utcnow() + \
            AuthLoginHandler.SESSION_LENGTH

    def get(self, user_id):
        '''
        Log in page (form).
        '''
        try:
            errormessage = self.get_argument("error")
        except:
            errormessage = ""

        next = self.get_argument("next", "/")

        with model.session_scope() as session:
            params = template.TemplateParams(session)
            theme_params = theme.ThemeParams(session)
            self.render(
                "../client/templates/login.html",
                params=params, theme=theme_params, next=next,
                error=errormessage)

    def post(self, user_id):
        '''
        Method for user to provide credentials and log in.
        '''
        email = self.get_argument("email", "")
        password = self.get_argument("password", "")
        try:
            with model.session_scope() as session:
                user = session.query(model.AppUser).\
                    filter(func.lower(model.AppUser.email) == func.lower(email)).\
                    one()
                if not user.password == password:
                    raise ValueError("Login incorrect")
                deleted = user.deleted or user.organisation.deleted
                session.expunge(user)
        except (sqlalchemy.orm.exc.NoResultFound, ValueError):
            self.clear_cookie("user")
            self.clear_cookie("superuser")
            error_msg = "?error=" + tornado.escape.url_escape("Login incorrect")
            self.redirect("/login/" + error_msg)
            return

        if deleted:
            self.clear_cookie("user")
            self.clear_cookie("superuser")
            error_msg = "?error=" + tornado.escape.url_escape(
                "Your account is inactive. Please contact an administrator")
            self.redirect("/login/" + error_msg)
            return

        self.set_secure_cookie(
            "user", str(user.id).encode('utf8'),
            expires=self.session_expires)
        if model.has_privillege(user.role, 'admin'):
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
        self.set_cookie(
            '_xsrf', token,
            expires=self.session_expires)
        return token

    @tornado.web.authenticated
    def put(self, user_id):
        '''
        Allows an admin to impersonate any other user without needing to know
        their password.
        '''
        superuser_id = self.get_secure_cookie('superuser')

        if superuser_id is None:
            raise errors.AuthzError("Not authorised: you are not a superuser")
        superuser_id = superuser_id.decode('utf8')
        with model.session_scope() as session:
            superuser = session.query(model.AppUser).get(superuser_id)
            if superuser is None or not model.has_privillege(
                    superuser.role, 'admin'):
                raise errors.MissingDocError(
                    "Not authorised: you are not a superuser")

            user = session.query(model.AppUser).get(user_id)
            if user is None:
                raise errors.MissingDocError("No such user")

            self._store_last_user(session);

            name = user.name
            log.warn('User %s is impersonating %s', superuser.email, user.email)
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

        if user_id is None:
            return;
        try:
            past_users = list(filter(lambda x: x['id'] != user_id, past_users))
        except KeyError:
            past_users = []

        log.warn('%s', user_id)
        user = session.query(model.AppUser).get(user_id)
        if user is None:
            return

        past_users.insert(0, {'id': user_id, 'name': user.name})
        past_users = past_users[:10]
        log.warn('%s', past_users)
        self.set_cookie('past-users', url_escape(
            json_encode(past_users), plus=False))


class AuthLogoutHandler(base_handler.BaseHandler):
    def get(self):
        self.clear_cookie("user")
        self.clear_cookie("superuser")
        self.redirect(self.get_argument("next", "/"))


def authz(*roles):
    '''
    Decorator to check whether a user is authorised. This only checks whether
    the user has the privilleges of a certain role. If not, a 403 error will be
    generated. Attach to a request handler method like this:

    @authz('org_admin', 'consultant')
    def get(self, path):
        ...
    '''
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            if not model.has_privillege(self.current_user.role, *roles):
                raise errors.AuthzError()
            return fn(self, *args, **kwargs)
        return wrapper
    return decorator
