# Handlers

import os
import re

import csscompressor
import slimit
import tornado.gen
import tornado.httpclient
import tornado.httputil
import tornado.options
import tornado.web

#import data


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
        'href': '/bower_components/bootstrap/dist/css/bootstrap.css'
    },
    {
        'cdn': '//maxcdn.bootstrapcdn.com/font-awesome/4.2.0/css/font-awesome.min.css', # @IgnorePep8
        'href': '/bower_components/font-awesome/css/font-awesome.css'
    },
    {
        'cdn': '//fonts.googleapis.com/css?family=Ubuntu',
        'href': '/fonts/Ubuntu.css'
    },
    {
        'min-href': '/minify/app.css',
        'href': '/css/app.css'
    },
]

SCRIPTS = [
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/jquery/2.1.1/jquery.min.js',
        'href': '/bower_components/jquery/dist/jquery.js'
    },
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/angularjs/1.3.14/angular.min.js', # @IgnorePep8
        'href': '/bower_components/angular/angular.js'
    },
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/angularjs/1.3.14/angular-route.min.js', # @IgnorePep8
        'href': '/bower_components/angular-route/angular-route.js'
    },
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/angularjs/1.3.14/angular-resource.min.js', # @IgnorePep8
        'href': '/bower_components/angular-resource/angular-resource.js'
    },
    {
        'cdn': '//ajax.googleapis.com/ajax/libs/angularjs/1.3.14/angular-animate.min.js', # @IgnorePep8
        'href': '/bower_components/angular-animate/angular-animate.js'
    },
    {
        'min-href': '/minify/3rd-party-min.js',
        'hrefs': [
            '/bower_components/angular-bootstrap/ui-bootstrap-tpls.js',
        ]
    },
    {
        'min-href': '/minify/app-min.js',
        'hrefs': [
            '/js/app.js',
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


class MinifyHandler(tornado.web.RequestHandler):
    '''
    Reduces the size of some text resources such as JavaScript and CSS files.

    Each minified resource has a list of sources; see the global SCRIPTS and
    STYLESHEETS objects.
    '''

    CACHE = {}

    def initialize(self, path, root):
        self.path = path
        self.root = root

    def get(self, path):
        path = self.path + path

        if path in MinifyHandler.CACHE:
            self.write_from_cache(path)
            return

        decl = None
        for s in SCRIPTS:
            if 'min-href' in s and s['min-href'] == path:
                decl = s
                break
        if decl is not None:
            print('Minifying JavaScript', path)
            self.add_to_cache(path, 'text/javascript', self.minify_js(decl))
            self.write_from_cache(path)
            return

        decl = None
        for s in STYLESHEETS:
            if 'min-href' in s and s['min-href'] == path:
                decl = s
                break
        if decl is not None:
            print('Minifying CSS', path)
            self.add_to_cache(path, 'text/css', self.minify_css(decl))
            self.write_from_cache(path)
            return

        raise tornado.web.HTTPError(
            400, "Specify text search terms using the 'value' paramter.")

    def add_to_cache(self, path, mimetype, text):
        MinifyHandler.CACHE[path] = {
            'mimetype': mimetype,
            'text': text
        }

    def write_from_cache(self, path):
        entry = MinifyHandler.CACHE[path]
        self.set_header("Content-Type", entry['mimetype'])
        self.write(entry['text'])
        self.finish()

    def minify_js(self, decl):
        if 'href' in decl:
            sources = [decl['href']]
        else:
            sources = decl['hrefs']

        text = self.read_all(sources)
        return slimit.minify(text, mangle=True)

    def minify_css(self, decl):
        if 'href' in decl:
            sources = [decl['href']]
        else:
            sources = decl['hrefs']

        text = self.read_all(sources)
        return csscompressor.compress(text)

    def read_all(self, sources):
        text = ""
        for s in sources:
            if s.startswith('/'):
                s = os.path.join(self.root, s[1:])
            else:
                s = os.path.join(self.root, s)
            with open(s, 'r') as f:
                text += f.read()
                text += '\n'
        return text
