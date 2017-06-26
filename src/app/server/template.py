import os
import time

from sqlalchemy import func
from tornado.escape import json_encode
import tornado.options
import tornado.web

import base_handler
import cache_bust
import config
import model
import theme
from utils import truthy

# A string to break through caches. This changes each time the app is deployed.
DEPLOY_ID = str(time.time())
aq_version = None


def deploy_id():
    if truthy(tornado.options.options.dev):
        return None
    else:
        return DEPLOY_ID


class TemplateParams:
    def __init__(self, session):
        self.session = session
        self.version = cache_bust.factory()

    @property
    def dev_mode(self):
        return truthy(tornado.options.options.dev) and 'true' or 'false'

    @property
    def is_training(self):
        return config.get_setting(self.session, 'is_training')

    @property
    def analytics_id(self):
        return tornado.options.options.analytics_id

    @property
    def aq_version(self):
        return aq_version

    @property
    def deploy_id(self):
        '''
        For assets that may need breakpoints. Under dev mode the URLs
        # will never change, and it's up to the developer to clear
        # their own cache. Under deployment the URLs will change.
        '''
        return deploy_id()

    @property
    def icon_query(self):
        '''
        For assets that don't need to be debugged but do need cache
        busting like favicons. Under both dev mode and deployment the
        URLs will change.
        '''
        # Always use a dev ID; this is f
        manifest_mod_time = (
            self.session.query(func.max(model.SystemConfig.modified))
                .limit(1)
                .scalar())
        if manifest_mod_time is not None:
            return "?v=conf-%s" % manifest_mod_time.timestamp()
        else:
            return "?v=conf-%s" % DEPLOY_ID

    @property
    def scripts(self):
        bower_versions = config.bower_versions()
        decls = config.get_resource('js_manifest')
        decls = config.deep_interpolate(decls, bower_versions)
        return self.prepare_resources(decls)

    @property
    def stylesheets(self):
        bower_versions = config.bower_versions()
        decls = config.get_resource('css_manifest')
        decls = config.deep_interpolate(decls, bower_versions)
        return self.prepare_resources(decls)

    @property
    def authz_declarations(self):
        decls = config.get_resource('authz')
        return json_encode(decls)

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
            if k != 'cdn':
                hrefs = [
                    '%s?v=%s' % (href, self.version(
                        rel='semi-volatile', dev='non-volatile'))
                    for href in hrefs]

            if dev_mode and k in {'cdn', 'min-href'}:
                print('Warning: using release resource in dev mode')
            elif not dev_mode and k in {'href', 'hrefs'}:
                print('Warning: using dev resource in release')

            resources.extend(hrefs)

        return resources


class TemplateHandler(base_handler.BaseHandler):
    '''
    Renders content from templates (e.g. index.html).
    '''

    def initialize(self, path):
        self.path = path

    @tornado.web.authenticated
    def get(self, path):
        if path == '':
            path = 'index.html'
        template = os.path.join(self.path, path)

        with model.session_scope() as session:
            params = TemplateParams(session)
            theme_params = theme.ThemeParams(session)
            self.render(
                template, params=params, theme=theme_params,
                user=self.current_user, organisation=self.organisation)


class UnauthenticatedTemplateHandler(base_handler.BaseHandler):
    def initialize(self, path):
        self.path = path

    def get(self, path):
        template = os.path.join(self.path, path)

        if path.endswith('.css'):
            self.set_header('Content-Type', 'text/css')

        with model.session_scope() as session:
            params = TemplateParams(session)
            theme_params = theme.ThemeParams(session)
            self.render(template, params=params, theme=theme_params)
