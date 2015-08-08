# Handlers

import functools
import logging
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
from tornado.escape import json_decode, json_encode


log = logging.getLogger('app.handlers')

# A string to break through caches. This changes each time Landblade is
# deployed.
DEPLOY_ID = str(time.time())


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
    def from_sa(cls, sa_error):
        log.error('%s', str(sa_error))
        match = cls.POSTGRES_PATTERN.search(str(sa_error))
        if match is not None:
            return cls(reason="Arguments are invalid: %s" % match.group(1))
        else:
            return cls()


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
            '/css/clock.css'
        ]
    },
    {
        'min-href': '/minify/3rd-party-min.css',
        'hrefs': [
            '/.bower_components/angular-hotkeys/build/hotkeys.css',
            '/.bower_components/angular-ui-select/dist/select.css',
            '/.bower_components/angular-ui-tree/dist/angular-ui-tree.min.css'
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
            '/.bower_components/angular-ui-select/dist/select.js',
            '/.bower_components/angular-ui-tree/dist/angular-ui-tree.js',
            '/.bower_components/angular-ui-sortable/sortable.js',
            '/.bower_components/jqueryui-touch-punch/jquery.ui.touch-punch.js'
        ]
    },
    {
        'min-href': '/minify/app-min.js',
        'hrefs': [
            '/js/app.js',
            '/js/admin.js',
            '/js/survey.js',
            '/js/survey-question.js',
            '/js/utils.js',
            '/js/widgets.js',
        ]
    }
]


class BaseHandler(tornado.web.RequestHandler):
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
            deploy_id=self.deploy_id)


class AuthLoginHandler(MainHandler):
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

        self.set_secure_cookie("user", str(user.id).encode('utf8'))
        if model.has_privillege(user.role, 'admin'):
            self.set_secure_cookie("superuser", str(user.id).encode('utf8'))
        self.redirect(self.get_argument("next", "/"))

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
            if superuser is None or not model.has_privillege(superuser.role, 'admin'):
                raise handlers.MissingDocError("Not authorised: you are not a superuser")

            user = session.query(model.AppUser).get(user_id)
            if user is None:
                raise handlers.MissingDocError("No such user")

            name = user.name
            log.warn('User %s is impersonating %s', superuser.email, user.email)
            self.set_secure_cookie("user", str(user.id).encode('utf8'))

        self.set_header("Content-Type", "text/plain")
        self.write("Impersonating %s" % name)
        self.finish()


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

    def paginate(self, query):
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

        query = query.limit(page_size)
        query = query.offset(page * page_size)
        return query

