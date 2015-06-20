#!/usr/bin/env python3

import base64
import inspect
import logging.config
import os

from alembic.config import Config
from alembic import command
from sqlalchemy import func
import sqlalchemy.orm
import tornado.options
import tornado.web

import data_access
import handlers
import model
from utils import truthy


log = logging.getLogger('app')
tornado.options.options.logging = 'none'


def get_package_dir():
    frameinfo = inspect.getframeinfo(inspect.currentframe())
    return os.path.dirname(frameinfo.filename)


def parse_options():
    package_dir = get_package_dir()

    tornado.options.define(
        "port", default=os.environ.get('PORT', '8000'),
        help="Bind to this port")

    logconf_path = os.path.join(package_dir, 'logging.cfg')
    if not os.path.exists(logconf_path):
        log.info("Warning: log config file %s does not exist.", logconf_path)
    else:
        logging.config.fileConfig(logconf_path)

    tornado.options.define(
        "xsrf", default=os.environ.get('AQ_XSRF', 'True'),
        help="Protect against XSRF attacks (default: True)")

    tornado.options.define(
        "dev", default=os.environ.get('DEV_MODE', 'True'),
        help="Development mode (default: True)")

    tornado.options.define(
        "debug", default=os.environ.get('DEBUG_MODE', 'True'),
        help="Debug mode (default: True)")

    tornado.options.define(
        "analytics_id", default=os.environ.get('ANALYTICS_ID', ''),
        help="Google Analytics ID, leave blank to disable (default: '')")

    tornado.options.parse_command_line()


def get_cookie_secret():
    with model.session_scope() as session:
        try:
            q = session.query(model.SystemConfig)
            conf = q.filter_by(name='cookie_secret').one()
        except sqlalchemy.orm.exc.NoResultFound:
            # TODO: Use a cookie secret dictionary, and cause keys to expire
            # after some time.
            log.info("Generating new cookie secret")
            secret = base64.b64encode(os.urandom(50)).decode('ascii')
            conf = model.SystemConfig(name='cookie_secret', value=secret)
            session.add(conf)
        return conf.value


def get_settings():
    package_dir = get_package_dir()
    return {
        "cookie_secret": get_cookie_secret(),
        "xsrf_cookies": truthy(tornado.options.options.xsrf),
        "debug": truthy(tornado.options.options.debug),
        "serve_traceback": truthy(tornado.options.options.dev),
        "gzip": True,
        "template_path": os.path.join(package_dir, "..", "client"),
        "login_url": "/login/",
    }


def database_upgrade():
    package_dir = get_package_dir()
    alembic_cfg = Config(os.path.join(package_dir, "..", "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location", os.path.join(package_dir, "..", "alembic"))
    if os.environ.get('DATABASE_URL') is not None:
        alembic_cfg.set_main_option("url", os.environ.get('DATABASE_URL'))

    try:
        command.upgrade(alembic_cfg, "head")
        log.info("Database version brought up to date")
    except sqlalchemy.exc.IntegrityError as e:
        log.error("Failed to upgrade database")
        raise
    except Exception as e:
        raise
        command.stamp(alembic_cfg, "head")
        log.info("Database versioning initialised")


def add_default_user():
    with model.session_scope() as session:
        count = session.query(func.count(model.AppUser.id)).scalar()
        if count == 0:
            log.info("First start. Creating default user %s", 'admin')
            org = model.Organisation(
                name="DEFAULT ORGANISATION", number_of_customers=0,
                region="NOWHERE")
            session.add(org)
            session.flush()
            user = model.AppUser(
                email="admin", name="DEFAULT USER", role="admin",
                organisation=org)
            user.set_password("admin")
            session.add(user)

def start_web_server():

    package_dir = get_package_dir()
    settings = get_settings()
    add_default_user()

    application = tornado.web.Application(
        [
            (r"/login/?(.*)", handlers.AuthLoginHandler, {
                'path': os.path.join(package_dir, "..", "client")}),
            (r"/logout/?", handlers.AuthLogoutHandler),
            (r"/()", handlers.MainHandler, {
                'path': '../client/index.html'}),

            (r"/bower_components/(.*)", tornado.web.StaticFileHandler, {
                'path': os.path.join(
                    package_dir, "..", "client", ".bower_components")}),
            (r"/minify/(.*)", handlers.MinifyHandler, {
                'path': '/minify/',
                'root': os.path.join(package_dir, "..", "client")}),
            (r"/(.*\.css)", handlers.CssHandler, {
                'root': os.path.join(package_dir, "..", "client")}),

            (r"/organisation/?(.*).json", data_access.OrgHandler, {}),
            (r"/user/?(.*).json", data_access.UserHandler, {}),

            (r"/(.*)", tornado.web.StaticFileHandler, {
                'path': os.path.join(package_dir, "..", "client")}),
        ], **settings
    )

    try:
        # If port is a string, *some* GNU/Linux systems try to look up the port
        # in /etc/services. So try to interpret it as an integer.
        # http://www.ducea.com/2006/09/11/error-servname-not-supported-for-ai_socktype/
        # https://github.com/pika/pika/issues/352#issuecomment-18704043
        port = int(tornado.options.options.port)
    except ValueError:
        port = tornado.options.options.port
    application.listen(port)

    if log.isEnabledFor(logging.INFO):
        import socket
        log.info("Settings: %s", settings)
        log.info(
            "Starting web application. Will be available on port %s", port)
        log.info("Try opening http://%s:%s", socket.gethostname(), port)
    tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    try:
        parse_options()
        database_upgrade()
        model.connect_db(os.environ.get('DATABASE_URL'))
        start_web_server()
    except KeyboardInterrupt:
        log.info("Shutting down due to user request (e.g. Ctrl-C)")
