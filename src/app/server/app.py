#!/usr/bin/env python3

import base64
from configparser import ConfigParser
import inspect
import logging.config
import os
import signal

from alembic.config import Config
from alembic import command
from sqlalchemy import func
import sqlalchemy.engine.reflection
import sqlalchemy.orm
import tornado
import tornado.httpserver
import tornado.options
import tornado.web


log = logging.getLogger('app')


def get_package_dir():
    frameinfo = inspect.getframeinfo(inspect.currentframe())
    return os.path.dirname(frameinfo.filename)


def configure_logging():
    package_dir = get_package_dir()
    # TODO: Stop using alembic command-line API so we can split this file up
    logconf_path = os.path.join(package_dir, "..", "alembic.ini")
    if not os.path.exists(logconf_path):
        log.info("Warning: log config file %s does not exist.", logconf_path)
    else:
        logging.config.fileConfig(logconf_path)


configure_logging()


import crud
import handlers
import import_handlers
import export_handlers
import statistics_handlers
import report_handlers
import model
from utils import truthy


tornado.options.options.logging = 'none'


def parse_options():
    package_dir = get_package_dir()

    tornado.options.define(
        "port", default=os.environ.get('PORT', '8000'),
        help="Bind to this port")

    tornado.options.define(
        "xsrf", default=os.environ.get('AQ_XSRF', 'True'),
        help="Protect against XSRF attacks (default: True)")

    tornado.options.define(
        "dev", default=os.environ.get('DEV_MODE', 'True'),
        help="Development mode (default: True)")

    tornado.options.define(
        "force_https", default=os.environ.get('FORCE_HTTPS', 'True'),
        help="Redirect to HTTPS when running on AWS (default: True)")

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
            conf.human_name = "Cookie Secret"
            conf.user_defined = False
            session.add(conf)
        return conf.value


def get_minimal_settings():
    package_dir = get_package_dir()
    return {
        "template_path": os.path.join(package_dir, "..", "client"),
        "login_url": "/login/",
        "cookie_secret": 'dummy'
    }


def get_settings():
    package_dir = get_package_dir()
    settings = get_minimal_settings()
    settings.update({
        "cookie_secret": get_cookie_secret(),
        "xsrf_cookies": truthy(tornado.options.options.xsrf),
        "debug": truthy(tornado.options.options.dev),
        "serve_traceback": truthy(tornado.options.options.dev),
        "gzip": True
    })
    return settings


def connect_db():
    package_dir = get_package_dir()
    alembic_cfg = Config(os.path.join(package_dir, "..", "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location", os.path.join(package_dir, "..", "alembic"))
    if os.environ.get('DATABASE_URL') is not None:
        alembic_cfg.set_main_option("sqlalchemy.url", os.environ.get('DATABASE_URL'))

    engine = model.connect_db(os.environ.get('DATABASE_URL'))
    inspector = sqlalchemy.engine.reflection.Inspector.from_engine(engine)

    # TODO: Don't use Alembic's command-line API! It also overrides stdout :(
    if 'alembic_version' not in inspector.get_table_names():
        log.info("Initialising database")
        model.initialise_schema(engine)
        command.stamp(alembic_cfg, "head")
    else:
        log.info("Upgrading database (if required)")
        command.upgrade(alembic_cfg, "head")

    model.connect_db_ro(os.environ.get('DATABASE_URL'))


def default_settings():
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

        setting = session.query(model.SystemConfig).get('pass_threshold')
        if setting is None:
            setting = model.SystemConfig(name='pass_threshold')
            setting.human_name = "Password Strength Threshold"
            setting.description = "The minimum strength for a password, " \
                "between 0.0 and 1.0, where 0.0 allows very weak passwords " \
                "and 1.0 requires strong passwords (default 0.85)."
            setting.user_defined = True
            setting.value = 0.85
            session.add(setting)

        setting = session.query(model.SystemConfig).get('adhoc_timeout')
        if setting is None:
            setting = model.SystemConfig(name='adhoc_timeout')
            setting.human_name = "Custom Query Time Limit"
            setting.description = "The maxium number of seconds a custom "\
                "query is allowed to run for (default 1.5)."
            setting.user_defined = True
            setting.value = 1.5
            session.add(setting)

        setting = session.query(model.SystemConfig).get('adhoc_max_limit')
        if setting is None:
            setting = model.SystemConfig(name='adhoc_max_limit')
            setting.human_name = "Custom Query Row Limit"
            setting.description = "The maxium number of rows a query can "\
                "return (default 2500)."
            setting.user_defined = True
            setting.value = 2500
            session.add(setting)


def get_mappings():
    package_dir = get_package_dir()
    return [
        (r"/login/?(.*)", handlers.AuthLoginHandler, {
            'path': os.path.join(package_dir, "..", "client")}),
        (r"/logout/?", handlers.AuthLogoutHandler),
        (r"/()", handlers.MainHandler, {
            'path': '../client/index.html'}),
        (r"/ping.*", handlers.PingHandler, {}),

        (r"/bower_components/(.*)", tornado.web.StaticFileHandler, {
            'path': os.path.join(
                package_dir, "..", "client", ".bower_components")}),
        (r"/minify/(.*)", handlers.MinifyHandler, {
            'path': '/minify/',
            'root': os.path.join(package_dir, "..", "client")}),
        (r"/(.*\.css)", handlers.CssHandler, {
            'root': os.path.join(package_dir, "..", "client")}),

        (r"/systemconfig.json", crud.config.SystemConfigHandler, {}),
        (r"/organisation/?([^/]*).json", crud.org.OrgHandler, {}),
        (r"/organisation/?([^/]*)/hierarchy/?([^/]*).json",
            crud.org.PurchasedSurveyHandler, {}),
        (r"/user/?([^/]*).json", crud.user.UserHandler, {}),
        (r"/user/([^/]*)/subscription/(.*).json",
            crud.activity.SubscriptionHandler, {}),
        (r"/activity/?([^/]*).json",
            crud.activity.ActivityHandler, {}),
        (r"/password.json", crud.user.PasswordHandler, {}),

        (r"/survey/?([^/]*).json", crud.survey.SurveyHandler, {}),
        (r"/survey/?([^/]*)/history.json", crud.survey.SurveyTrackingHandler, {}),
        (r"/hierarchy/?([^/]*).json", crud.hierarchy.HierarchyHandler, {}),
        (r"/hierarchy/?([^/]*)/survey.json", crud.survey.SurveyHistoryHandler, {
            'mapper': model.Hierarchy}),
        (r"/qnode/?([^/]*).json", crud.qnode.QuestionNodeHandler, {}),
        (r"/qnode/?([^/]*)/survey.json", crud.survey.SurveyHistoryHandler, {
            'mapper': model.QuestionNode}),
        (r"/measure/?([^/]*).json", crud.measure.MeasureHandler, {}),
        (r"/measure/?([^/]*)/survey.json", crud.survey.SurveyHistoryHandler, {
            'mapper': model.Measure}),

        (r"/assessment/?([^/]*).json", crud.assessment.AssessmentHandler, {}),
        (r"/assessment/([^/]*)/rnode/?([^/]*).json",
            crud.rnode.ResponseNodeHandler, {}),
        (r"/assessment/([^/]*)/response/?([^/]*).json",
            crud.response.ResponseHandler, {}),
        (r"/assessment/([^/]*)/response/?([^/]*)/history.json",
            crud.response.ResponseHistoryHandler, {}),
        (r"/assessment/([^/]*)/measure/([^/]*)/attachment.json",
            crud.attachment.ResponseAttachmentsHandler, {}),
        (r"/attachment/([^/]*).json",
            crud.attachment.AttachmentHandler, {}),

        (r"/statistics/([^/]*).json",
            statistics_handlers.StatisticsHandler, {}),
        (r"/diff.json",
            report_handlers.DiffHandler, {}),
        (r"/export/survey/([^/]*)/hierarchy/([^/]*)\.(.+)",
            export_handlers.ExportSurveyHandler, {}),
        (r"/export/assessment/([^/]*)\.(.+)",
            export_handlers.ExportAssessmentHandler, {}),
        (r"/export/response/([^/]*)\.(.+)",
            export_handlers.ExportResponseHandler, {}),
        (r"/adhoc_query\.(.+)",
            report_handlers.AdHocHandler, {}),
        (r"/reformat.sql",
            report_handlers.SqlFormatHandler, {}),

        (r"/import/structure.json", import_handlers.ImportStructureHandler, {}),
        (r"/import/response.json", import_handlers.ImportResponseHandler, {}),
        (r"/import/assessment.json", import_handlers.ImportAssessmentHandler, {}),
        (r"/redirect", handlers.RedirectHandler),

        (r"/(.*)", tornado.web.StaticFileHandler, {
            'path': os.path.join(package_dir, "..", "client")}),
    ]


def start_web_server():

    package_dir = get_package_dir()
    settings = get_settings()
    default_settings()

    application = tornado.web.Application(get_mappings(), **settings)

    try:
        # If port is a string, *some* GNU/Linux systems try to look up the port
        # in /etc/services. So try to interpret it as an integer.
        # http://www.ducea.com/2006/09/11/error-servname-not-supported-for-ai_socktype/
        # https://github.com/pika/pika/issues/352#issuecomment-18704043
        port = int(tornado.options.options.port)
    except ValueError:
        port = tornado.options.options.port
    max_buffer_size = 10 * 1024**2 # 10MB
    http_server = tornado.httpserver.HTTPServer(application, max_body_size=max_buffer_size)
    http_server.listen(port)

    if log.isEnabledFor(logging.INFO):
        import socket
        log.info("Tornado version: %s", tornado.version)
        log.info("Tornado settings: %s", settings)
        log.info(
            "Starting web application. Will be available on port %s", port)
        log.info("Try opening http://%s:%s", socket.gethostname(), port)
    tornado.ioloop.IOLoop.instance().start()


def signal_handler(signum, frame):
    tornado.ioloop.IOLoop.instance().add_callback_from_signal(stop_web_server)


def stop_web_server():
    log.warn("Server shutdown due to signal")
    tornado.ioloop.IOLoop.instance().stop()


def read_app_version():
    package_dir = get_package_dir()
    try:
        with open(os.path.join(package_dir, '..', 'version.txt')) as f:
            version = f.readline().strip()
    except FileNotFoundError:
        version = None
    handlers.aq_version = version


if __name__ == "__main__":
    try:
        parse_options()
        connect_db()
        read_app_version()
        signal.signal(signal.SIGTERM, signal_handler)
        start_web_server()
    except KeyboardInterrupt:
        log.info("Shutting down due to user request (e.g. Ctrl-C)")
