# Handlers

import logging
import os
import re

import sass
#import slimit
import tornado.gen
import tornado.httpclient
import tornado.httputil
import tornado.options
import tornado.web

#import data


log = logging.getLogger('app.handlers')


class ModelError(tornado.web.HTTPError):
    def __init__(self, log_message=None, *args, **kwargs):
        tornado.web.HTTPError.__init__(
            self, 403, log_message=log_message, *args, **kwargs)


class MissingDocError(tornado.web.HTTPError):
    def __init__(self, log_message=None, *args, **kwargs):
        tornado.web.HTTPError.__init__(
            self, 404, log_message=log_message, *args, **kwargs)


class InternalModelError(tornado.web.HTTPError):
    def __init__(self, log_message=None, *args, **kwargs):
        tornado.web.HTTPError.__init__(
            self, 500, log_message=log_message, *args, **kwargs)


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
        'cdn': '//maxcdn.bootstrapcdn.com/font-awesome/4.2.0/css/font-awesome.min.css', # @IgnorePep8
        'href': '/.bower_components/font-awesome/css/font-awesome.css'
    },
    {
        'cdn': '//fonts.googleapis.com/css?family=Ubuntu',
        'href': '/fonts/Ubuntu.css'
    },
    {
        'min-href': '/minify/app-min.css',
        'href': '/css/app.css'
    },
    {
        'min-href': '/minify/3rd-party-min.css',
        'hrefs': [
            '/.bower_components/angular-hotkeys/build/hotkeys.css',
        ]
    },
]

SCRIPTS = [
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/jquery/2.1.1/jquery.min.js',
        'href': '/.bower_components/jquery/dist/jquery.js'
    },
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/angularjs/1.3.14/angular.min.js', # @IgnorePep8
        'href': '/.bower_components/angular/angular.js'
    },
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/angularjs/1.3.14/angular-route.min.js', # @IgnorePep8
        'href': '/.bower_components/angular-route/angular-route.js'
    },
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/angularjs/1.3.14/angular-resource.min.js', # @IgnorePep8
        'href': '/.bower_components/angular-resource/angular-resource.js'
    },
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/angularjs/1.3.14/angular-animate.min.js', # @IgnorePep8
        'href': '/.bower_components/angular-animate/angular-animate.js'
    },
    {
        'min-href': '/minify/3rd-party-min.js',
        'hrefs': [
            '/.bower_components/angular-bootstrap/ui-bootstrap-tpls.js',
            '/.bower_components/angular-hotkeys/build/hotkeys.js'
        ]
    },
    {
        'min-href': '/minify/app-min.js',
        'hrefs': [
            '/js/app.js',
            '/js/survey.js',
            '/js/utils.js',
            '/js/widgets.js',
        ]
    }
]


class MainHandler(tornado.web.RequestHandler):
    '''
    Renders content from templates.
    '''

    def initialize(self, path):
        self.path = path

        self.scripts = self.prepare_resources(SCRIPTS)
        self.stylesheets = self.prepare_resources(STYLESHEETS)

    def prepare_resources(self, declarations):
        '''
        Resolve a list of resources. Different URLs will be used for the
        resources depending on whether the application is running in
        development or release mode.
        '''
        resources = []
        if tornado.options.options.dev in {'True', 'true'}:
            for sdef in declarations:
                if 'href' in sdef:
                    resources.append(sdef['href'])
                elif 'hrefs' in sdef:
                    resources.extend(sdef['hrefs'])
                elif 'min-href' in sdef:
                    print('Warning: using minified resource in dev mode')
                    resources.append(sdef['min-href'])
                elif 'cdn' in sdef:
                    print('Warning: using remote resource in dev mode')
                    resources.append(sdef['cdn'])
                else:
                    print('Warning: unrecognised resource')
        else:
            for sdef in declarations:
                if 'cdn' in sdef:
                    resources.append(sdef['cdn'])
                elif 'min-href' in sdef:
                    resources.append(sdef['min-href'])
                elif 'href' in sdef:
                    print('Warning: using unminified resource in relese mode')
                    resources.append(sdef['href'])
                elif 'hrefs' in sdef:
                    print('Warning: using unminified resource in relese mode')
                    resources.extend(sdef['hrefs'])
                else:
                    print('Warning: unrecognised resource')
        return resources

    def get(self, path):
        if path != "":
            template = os.path.join(self.path, path)
        else:
            template = self.path

        self.render(
            template, scripts=self.scripts, stylesheets=self.stylesheets,
            analytics_id=tornado.options.options.analytics_id)


class RamCacheHandler(tornado.web.RequestHandler):

    CACHE = {}

    def get(self, path):
        qpath = self.resolve_path(path)
        if qpath in RamCacheHandler.CACHE and tornado.options.options.dev not in {'True', 'true'}:
            self.write_from_cache(qpath)
        else:
            log.info('Generating %s', path)
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
            with open(s, 'r') as f:
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
        log.info("Compiling CSS for %s", path)
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
