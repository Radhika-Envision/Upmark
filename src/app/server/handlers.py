# Handlers

import functools
import logging
from math import ceil
import os
import re
import time

import sass
import tornado.gen
import tornado.httpclient
import tornado.httputil
import tornado.options
import tornado.web
import sqlalchemy
from sqlalchemy.sql import func

import model 

from utils import denormalise, falsy, truthy
from tornado.escape import json_decode, json_encode, url_escape, url_unescape


log = logging.getLogger('app.handlers')

# A string to break through caches. This changes each time Landblade is
# deployed.
DEPLOY_ID = str(time.time())
aq_version = None


def deploy_id():
    if truthy(tornado.options.options.dev):
        return None
    else:
        return DEPLOY_ID


class AuthzError(tornado.web.HTTPError):
    def __init__(self, reason="Not authorised", log_message=None, *args, **kwargs):
        tornado.web.HTTPError.__init__(
            self, 403, reason=reason, log_message=log_message, *args, **kwargs)


class ModelError(tornado.web.HTTPError):
    def __init__(self, reason="Arguments are invalid", log_message=None, *args, **kwargs):
        tornado.web.HTTPError.__init__(
            self, 403, reason=reason, log_message=log_message, *args, **kwargs)

    POSTGRES_PATTERN = re.compile(r'\([^)]+\) (.*)')

    @classmethod
    def from_sa(cls, sa_error, reason="Arguments are invalid: "):
        log.error('%s', str(sa_error))
        match = cls.POSTGRES_PATTERN.search(str(sa_error))
        if match is not None:
            return cls(reason="%s%s" % (reason, match.group(1)))
        else:
            return cls(reason=reason)


class MissingDocError(tornado.web.HTTPError):
    def __init__(self, reason="Document not found", log_message=None, *args, **kwargs):
        tornado.web.HTTPError.__init__(
            self, 404, reason=reason, log_message=log_message, *args, **kwargs)


class MethodError(tornado.web.HTTPError):
    def __init__(self, reason="Method not allowed", log_message=None, *args, **kwargs):
        tornado.web.HTTPError.__init__(
            self, 405, reason=reason, log_message=log_message, *args, **kwargs)


class InternalModelError(tornado.web.HTTPError):
    def __init__(self, reason="Bug in data model", log_message=None, *args, **kwargs):
        tornado.web.HTTPError.__init__(
            self, 500, reason=reason, log_message=log_message, *args, **kwargs)


# Resources that have a CDN mirror have a local 'href' and a remote 'cdn'.
# Resources that have no CDN (or no CDN supporting both HTTP and HTTPS)
# have a local 'min-href' and a list of local 'hrefs'. 'min-href' is used
# in production mode; in that case the minify handler may compress the
# sources (if 'min-href' points to an endpoint handled by the
# MinifyHandler).
#
# CARE must be taken when grouping scripts: make sure they will be concatenated
# in the right order, and make sure they all use strict mode or not (not a
# mixture).

STYLESHEETS = [
    {
        'cdn': '//maxcdn.bootstrapcdn.com/bootstrap/3.2.0/css/bootstrap.min.css', # @IgnorePep8
        'href': '/.bower_components/bootstrap/dist/css/bootstrap.css'
    },
    {
        'cdn': '//maxcdn.bootstrapcdn.com/font-awesome/4.4.0/css/font-awesome.min.css', # @IgnorePep8
        'href': '/.bower_components/font-awesome/css/font-awesome.css'
    },
    {
        'cdn': '//fonts.googleapis.com/css?family=Ubuntu',
        'href': '/fonts/Ubuntu.css'
    },
    {
        'min-href': '/minify/app-min.css',
        'hrefs': [
            '/css/app.css',
            '/css/dropzone.css',
            '/css/clock.css',
            '/css/statistics.css'
        ]
    },
    {
        'min-href': '/minify/3rd-party-min.css',
        'hrefs': [
            '/.bower_components/angular-hotkeys/build/hotkeys.css',
            '/.bower_components/angular-ui-select/dist/select.css',
            '/.bower_components/angular-ui-tree/dist/angular-ui-tree.min.css',
            '/.bower_components/medium-editor/dist/css/medium-editor.min.css',
            '/.bower_components/medium-editor/dist/css/themes/default.min.css'
        ]
    },
]

SCRIPTS = [
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/jquery/2.1.1/jquery.min.js',
        'href': '/.bower_components/jquery/dist/jquery.js'
    },
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/angularjs/1.4.3/angular.min.js', # @IgnorePep8
        'href': '/.bower_components/angular/angular.js'
    },
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/angularjs/1.4.3/angular-cookies.min.js', # @IgnorePep8
        'href': '/.bower_components/angular-cookies/angular-cookies.js'
    },
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/angularjs/1.4.3/angular-route.min.js', # @IgnorePep8
        'href': '/.bower_components/angular-route/angular-route.js'
    },
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/angularjs/1.4.3/angular-resource.min.js', # @IgnorePep8
        'href': '/.bower_components/angular-resource/angular-resource.js'
    },
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/angularjs/1.4.3/angular-animate.min.js', # @IgnorePep8
        'href': '/.bower_components/angular-animate/angular-animate.js'
    },
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/angularjs/1.4.3/angular-sanitize.min.js', # @IgnorePep8
        'href': '/.bower_components/angular-sanitize/angular-sanitize.js'
    },
    {
        'cdn': '//code.jquery.com/ui/1.11.4/jquery-ui.min.js',
        'href': '/.bower_components/jquery-ui/jquery-ui.js'
    },
    {
        'min-href': '/minify/3rd-party-min.js',
        'hrefs': [
            '/.bower_components/bootstrap/dist/js/bootstrap.js',
            '/.bower_components/angular-bootstrap/ui-bootstrap-tpls.js',
            '/.bower_components/angular-hotkeys/build/hotkeys.js',
            '/.bower_components/angular-bootstrap-show-errors/src/showErrors.js',
            '/.bower_components/angular-validation-match/dist/angular-validation-match.js',
            '/.bower_components/angular-select-text/src/angular-select-text.js',
            '/.bower_components/angular-timeago/dist/angular-timeago.js',
            '/.bower_components/angular-ui-select/dist/select.js',
            '/.bower_components/angular-ui-tree/dist/angular-ui-tree.js',
            '/.bower_components/angular-ui-sortable/sortable.js',
            '/.bower_components/dropzone/dist/dropzone.js',
            '/.bower_components/jqueryui-touch-punch/jquery.ui.touch-punch.js',
            '/.bower_components/js-expression-eval/parser.js',
            '/.bower_components/d3/d3.min.js',
            '/.bower_components/medium-editor/dist/js/medium-editor.js',
            '/.bower_components/angular-medium-editor/dist/angular-medium-editor.js',
            '/.bower_components/megamark/dist/megamark.js',
            '/.bower_components/angular-diff-match-patch/angular-diff-match-patch.js',
            '/.bower_components/google-diff-match-patch/diff_match_patch.js',
            '/.bower_components/domador/dist/domador.js',
            '/.bower_components/FileSaver.js/FileSaver.js'
        ]
    },
    {
        'min-href': '/minify/app-min.js',
        'hrefs': [
            '/js/app.js',
            '/js/admin.js',
            '/js/survey.js',
            '/js/survey-question.js',
            '/js/survey-answer.js',
            '/js/utils.js',
            '/js/widgets.js',
        ]
    }
]


class BaseHandler(tornado.web.RequestHandler):

    def prepare(self):
        if (truthy(tornado.options.options.force_https) and
            'X-Forwarded-Proto' in self.request.headers and
            self.request.headers['X-Forwarded-Proto'] != 'https'):
            self.redirect(re.sub(r'^([^:]+)', 'https', self.request.full_url()))

    def get_current_user(self):
        # Cached value is available in current_user property.
        # http://tornado.readthedocs.org/en/latest/web.html#tornado.web.RequestHandler.current_user
        uid = self.get_secure_cookie('user')
        if uid is None:
            return None
        uid = uid.decode('utf8')
        with model.session_scope() as session:
            try:
                user = session.query(model.AppUser).get(uid)
                if not user.enabled:
                    superuser = self.get_secure_cookie('superuser')
                    if superuser is None:
                        return None
            except sqlalchemy.exc.StatementError:
                return None
            if user is not None:
                session.expunge(user)
            return user

    def has_privillege(self, *roles):
        return model.has_privillege(self.current_user.role, *roles)

    def check_privillege(self, *roles):
        if not self.has_privillege(*roles):
            raise AuthzError()

    @property
    def organisation(self):
        if self.current_user is None or self.current_user.organisation_id is None:
            return None
        with model.session_scope() as session:
            organisation = session.query(model.Organisation).\
                get(self.current_user.organisation_id)
            session.expunge(organisation)
            return organisation

    @property
    def request_son(self):
        try:
            return self._request_son
        except AttributeError:
            try:
                self._request_son = denormalise(json_decode(self.request.body))
            except (TypeError, UnicodeError, ValueError) as e:
                raise ModelError(
                    "Could not decode request body: %s. Body started with %s" %
                    (str(e), self.request.body[0:30]))
            return self._request_son

    def set_status(self, *args, **kwargs):
        reason = kwargs.get('reason')
        if reason:
            self.reason(reason)
        return super().set_status(*args, **kwargs)

    def reason(self, message):
        self.add_header("Operation-Details", message)


class PingHandler(BaseHandler):
    '''
    Handler for load balancer health checks. For configuring AWS ELB, see:
    https://docs.aws.amazon.com/ElasticLoadBalancing/latest/DeveloperGuide/elb-healthchecks.html
    '''

    def get(self):
        # Check that the connection to the database works
        with model.session_scope() as session:
            session.query(model.SystemConfig).count()

        self.set_header("Content-Type", "text/plain")
        self.write("Web services are UP")
        self.finish()


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
                raise AuthzError()
            return fn(self, *args, **kwargs)
        return wrapper
    return decorator


class MainHandler(BaseHandler):
    '''
    Renders content from templates.
    '''

    def initialize(self, path):
        self.path = path

        self.deploy_id = deploy_id()
        self.scripts = self.prepare_resources(SCRIPTS)
        self.stylesheets = self.prepare_resources(STYLESHEETS)

    def prepare_resources(self, declarations):
        '''
        Resolve a list of resources. Different URLs will be used for the
        resources depending on whether the application is running in
        development or release mode.
        '''
        resources = []
        dev_mode = truthy(tornado.options.options.dev)

        link_order = ['cdn', 'min-href', 'href', 'hrefs']
        if dev_mode:
            link_order.reverse()

        for sdef in declarations:
            # Convert dictionary to ordered list of tuples (based on precedence)
            rs = ((k, sdef[k]) for k in link_order if k in sdef)
            try:
                k, hrefs = next(rs)
            except KeyError:
                print('Warning: unrecognised resource')
                continue
            if isinstance(hrefs, str):
                hrefs = [hrefs]

            # Add a resource deployment version number to bust the cache, except
            # for CDN links.
            if self.deploy_id and k != 'cdn':
                hrefs = ['%s?v=%s' % (href, self.deploy_id) for href in hrefs]

            if dev_mode and k in {'cdn', 'min-href'}:
                print('Warning: using release resource in dev mode')
            elif not dev_mode and k in {'href', 'hrefs'}:
                print('Warning: using dev resource in release')

            resources.extend(hrefs)

        return resources

    @tornado.web.authenticated
    def get(self, path):
        if path != "":
            template = os.path.join(self.path, path)
        else:
            template = self.path

        self.render(
            template, user=self.current_user, organisation=self.organisation,
            scripts=self.scripts, stylesheets=self.stylesheets,
            analytics_id=tornado.options.options.analytics_id,
            deploy_id=self.deploy_id,
            aq_version=aq_version)


class AuthLoginHandler(MainHandler):
    EXPIRE_DAYS = 30

    def get(self, user_id):
        '''
        Log in page (form).
        '''
        try:
            errormessage = self.get_argument("error")
        except:
            errormessage = ""

        self.render(
            "../client/login.html", scripts=self.scripts,
            stylesheets=self.stylesheets,
            analytics_id=tornado.options.options.analytics_id,
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
                if not user.check_password(password):
                    raise ValueError("Login incorrect")
                session.expunge(user)
        except (sqlalchemy.orm.exc.NoResultFound, ValueError):
            self.clear_cookie("user")
            self.clear_cookie("superuser")
            error_msg = "?error=" + tornado.escape.url_escape("Login incorrect")
            self.redirect("/login/" + error_msg)
            return

        if not user.enabled:
            self.clear_cookie("user")
            self.clear_cookie("superuser")
            error_msg = "?error=" + tornado.escape.url_escape(
                "Your account is inactive. Please contact an administrator")
            self.redirect("/login/" + error_msg)
            return

        self.set_secure_cookie(
            "user", str(user.id).encode('utf8'),
            expires_days=AuthLoginHandler.EXPIRE_DAYS)
        if model.has_privillege(user.role, 'admin'):
            self.set_secure_cookie(
                "superuser", str(user.id).encode('utf8'),
                expires_days=AuthLoginHandler.EXPIRE_DAYS)

        self.redirect(self.get_argument("next", "/"))

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
            expires_days=AuthLoginHandler.EXPIRE_DAYS)
        return token

    @tornado.web.authenticated
    def put(self, user_id):
        '''
        Allows an admin to impersonate any other user without needing to know
        their password.
        '''
        superuser_id = self.get_secure_cookie('superuser')

        if superuser_id is None:
            raise AuthzError("Not authorised: you are not a superuser")
        superuser_id = superuser_id.decode('utf8')
        with model.session_scope() as session:
            superuser = session.query(model.AppUser).get(superuser_id)
            if superuser is None or not model.has_privillege(
                    superuser.role, 'admin'):
                raise handlers.MissingDocError(
                    "Not authorised: you are not a superuser")

            user = session.query(model.AppUser).get(user_id)
            if user is None:
                raise handlers.MissingDocError("No such user")

            self._store_last_user(session);

            name = user.name
            log.warn('User %s is impersonating %s', superuser.email, user.email)
            self.set_secure_cookie(
                "user", str(user.id).encode('utf8'),
                expires_days=AuthLoginHandler.EXPIRE_DAYS)
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


class AuthLogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie("user")
        self.clear_cookie("superuser")
        self.redirect(self.get_argument("next", "/"))


class RamCacheHandler(tornado.web.RequestHandler):

    CACHE = {}

    def get(self, path):
        qpath = self.resolve_path(path)
        if qpath in RamCacheHandler.CACHE and falsy(tornado.options.options.dev):
            self.write_from_cache(qpath)
        else:
            log.debug('Generating %s', path)
            mimetype, text = self.generate(path)
            self.add_to_cache(qpath, mimetype, text)
            self.write_from_cache(qpath)

    def resolve_path(self, path):
        return path

    def generate(self, path):
        raise tornado.web.HTTPError(
            404, "Path %s not found in cache.", path)

    def add_to_cache(self, path, mimetype, text):
        RamCacheHandler.CACHE[path] = {
            'mimetype': mimetype,
            'text': text
        }

    def write_from_cache(self, path):
        entry = RamCacheHandler.CACHE[path]
        self.set_header("Content-Type", entry['mimetype'])
        self.write(entry['text'])
        self.finish()


def resolve_file(path, extension_map):
    if os.path.exists(path):
        return path

    if extension_map is None:
        extension_map = {}

    extensions = list(extension_map.items())
    # Add one phony, empty extension
    extensions.insert(0, ("", [""]))

    for ext1, vs in extensions:
        if not path.endswith(ext1):
            continue
        if len(ext1) > 0:
            base_path = path[:-len(ext1)]
        else:
            base_path = path
        for ext2 in vs:
            p = base_path + ext2
            if os.path.exists(p):
                return p

    raise FileNotFoundError("No such file %s." % path)


class MinifyHandler(RamCacheHandler):
    '''
    Reduces the size of some text resources such as JavaScript and CSS files.

    Each minified resource has a list of sources; see the global SCRIPTS and
    STYLESHEETS objects.
    '''

    def initialize(self, path, root):
        self.path = path
        self.root = os.path.abspath(root)

    def resolve_path(self, path):
        return self.path + path

    def generate(self, path):
        path = self.resolve_path(path)

        decl = None
        for s in SCRIPTS:
            if 'min-href' in s and s['min-href'] == path:
                decl = s
                break
        if decl is not None:
            return 'text/javascript', self.minify_js(decl)

        decl = None
        for s in STYLESHEETS:
            if 'min-href' in s and s['min-href'] == path:
                decl = s
                break
        if decl is not None:
            return 'text/css', self.minify_css(decl)

        raise tornado.web.HTTPError(
            400, "No matching minification declaration.")

    def minify_js(self, decl):
        if 'href' in decl:
            sources = [decl['href']]
        else:
            sources = decl['hrefs']

        text = self.read_all(sources)
        # FIXME: slimit is broken on Python 3. For now, just concatenate sources
        # https://github.com/rspivak/slimit/issues/64
        return text
        #return slimit.minify(text, mangle=True)

    def minify_css(self, decl):
        if 'href' in decl:
            sources = [decl['href']]
        else:
            sources = decl['hrefs']

        text = ""
        for s in sources:
            if s.startswith('/'):
                s = os.path.join(self.root, s[1:])
            else:
                s = os.path.join(self.root, s)
            s = resolve_file(s, extension_map={'.css': ['.scss']})
            text += sass.compile(filename=s, output_style='compressed')
            text += "\n"
        return text

    def read_all(self, sources, extension_map=None):
        text = ""
        for s in sources:
            if s.startswith('/'):
                s = os.path.join(self.root, s[1:])
            else:
                s = os.path.join(self.root, s)
            s = resolve_file(s, extension_map)
            s = os.path.abspath(s)
            if not s.startswith(self.root):
                raise tornado.web.HTTPError(
                    404, "No such file %s." % s)
            with open(s, 'r', encoding='utf8') as f:
                text += f.read()
            text += "\n"
        return text


class CssHandler(RamCacheHandler):
    '''
    Converts funky CSS formats to regular CSS. This is generally used in
    non-minification mode; the MinifyHandler also compiles SASS.
    '''

    def initialize(self, root):
        self.root = os.path.abspath(root)

    def generate(self, path):
        path = self.resolve_path(path)
        log.debug("Compiling CSS for %s", path)
        if path.startswith('/'):
            path = os.path.join(self.root, path[1:])
        else:
            path = os.path.join(self.root, path)

        try:
            path = resolve_file(path, extension_map={'.css': ['.scss']})
        except FileNotFoundError:
            raise tornado.web.HTTPError(
                404, "No such file %s." % path)

        if not path.startswith(self.root):
            raise tornado.web.HTTPError(
                404, "No such file %s." % path)

        return 'text/css', sass.compile(filename=path)


class Paginate:
    '''
    Mixin to support pagination.
    '''
    MAX_PAGE_SIZE = 100

    def paginate(self, query, optional=False):
        if optional and self.get_argument("page", None) is None:
            return query

        page_size = self.get_argument("pageSize", str(Paginate.MAX_PAGE_SIZE))
        try:
            page_size = int(page_size)
        except ValueError:
            raise handlers.ModelError("Invalid page size")
        if page_size > Paginate.MAX_PAGE_SIZE:
            raise handlers.ModelError(
                "Page size is too large (max %d)" % Paginate.MAX_PAGE_SIZE)

        page = self.get_argument("page", "0")
        try:
            page = int(page)
        except ValueError:
            raise handlers.ModelError("Invalid page")
        if page < 0:
            raise handlers.ModelError("Page must be non-negative")

        num_items = query.count()
        self.set_header('Page-Count', "%d" % ceil(num_items / page_size))
        self.set_header('Page-Index', "%d" % page)
        self.set_header('Page-Item-Count', "%d" % page_size)

        query = query.limit(page_size)
        query = query.offset(page * page_size)
        return query

