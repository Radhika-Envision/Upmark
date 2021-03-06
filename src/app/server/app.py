#!/usr/bin/env python3

import base64
import logging.config
import os
import re
import signal
import socket
from ssl import SSLError, SSLEOFError

from sqlalchemy import func
import sqlalchemy.orm
import tornado
import tornado.httpclient
import tornado.httpserver
import tornado.options
import tornado.web

import configure_logging  # noqa: F401

import authn
import compile_handlers
import crud
from importer.prog_import import ImportStructureHandler
from importer.sub_import import ImportSubmissionHandler
import model
import protocol
import report.custom
from report.diff import DiffHandler
from report.prog_export import ExportProgramHandler
from report.sub_export import ExportSubmissionHandler
from report.sub_stats import StatisticsHandler
from report.sub_temporal import TemporalReportHandler
from report.exportAssetReport import ExportAssetHandler
import template
from utils import get_package_dir, truthy


log = logging.getLogger('app')
tornado.options.options.logging = 'none'


def ssl_log_filter(record):
    '''
    Ignore some SSL errors which may occur if a client tries to use unsupported
    ciphers/protocols.
    '''
    # http://stackoverflow.com/a/26936729/320036
    if record.exc_info is not None:
        e = record.exc_info[1]
    elif len(record.args) >= 3 and isinstance(record.args[2], Exception):
        e = record.args[2]
    else:
        e = None

    if isinstance(e, SSLEOFError):
        return False
    if isinstance(e, SSLError):
        if e.reason in {'NO_SHARED_CIPHER'}:
            return False

    return True


def parse_options():
    tornado.options.define(
        "port", default=os.environ.get('PORT', '8000'),
        help="Bind to this port")

    tornado.options.define(
        "xsrf", default=os.environ.get('AQ_XSRF') or 'True',
        help="Protect against XSRF attacks (default: True)")

    tornado.options.define(
        "dev", default=os.environ.get('DEV_MODE') or 'True',
        help="Development mode (default: True)")

    tornado.options.define(
        "force_https", default=os.environ.get('FORCE_HTTPS') or 'True',
        help="Redirect to HTTPS when running on AWS (default: True)")

    tornado.options.define(
        "analytics_id", default=os.environ.get('ANALYTICS_ID', ''),
        help="Google Analytics ID, leave blank to disable (default: '')")

    tornado.options.parse_command_line()


def get_cookie_secret():
    with model.session_scope() as session:
        try:
            q = session.query(model.SystemConfig)
            conf = q.filter_by(name='_cookie_secret').one()
        except sqlalchemy.orm.exc.NoResultFound:
            # TODO: Use a cookie secret dictionary, and cause keys to expire
            # after some time.
            log.info("Generating new cookie secret")
            secret = base64.b64encode(os.urandom(50)).decode('ascii')
            conf = model.SystemConfig(name='_cookie_secret', value=secret)
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
    db_url = model.get_database_url()
    model.connect_db(db_url)
    try:
        model.connect_db_ro(db_url)
    except model.MissingUser:
        # This shouldn't happen because the user is created as part of the
        # schema. However if the user is accidentally deleted - or if the
        # database is restored from backup before the app is started for the
        # first time - then this is the easiest way to get the user back.
        model.create_analyst_user()
        model.connect_db_ro(db_url)
    except model.WrongPassword:
        # If the database is restored from a backup, the analyst password might
        # be wrong.
        model.reset_analyst_password()
        model.connect_db_ro(db_url)


def default_settings():
    with model.session_scope() as session:
        count = session.query(func.count(model.AppUser.id)).scalar()
        if count == 0:
            log.info("First start. Creating default user %s", 'admin')
            org = model.Organisation(name="DEFAULT ORGANISATION")
            session.add(org)
            session.flush()
            user = model.AppUser(
                email="admin", name="DEFAULT USER", role="super_admin",
                organisation=org, password="admin")
            session.add(user)

            surveygroup = model.SurveyGroup(title="Upmark")
            org.surveygroups.add(surveygroup)
            user.surveygroups.add(surveygroup)
            session.add(surveygroup)


def get_mappings():
    package_dir = get_package_dir()
    return [
        (r"/login/?",
            authn.LoginHandler, {
                'path': os.path.join(package_dir, "..", "client")}),
        (r"/impersonate/(.*)",
            authn.ImpersonateHandler, {}),
        (r"/logout/?",
            authn.LogoutHandler),
        (r"/()",
            template.TemplateHandler, {'path': '../client/templates/'}),
        (r"/(.*\.html)",
            tornado.web.StaticFileHandler, {
                'path': os.path.join(package_dir, "../client/templates/")}),
        (r"/(manifest.json|css/user_style.css)",
            template.UnauthenticatedTemplateHandler, {
                'path': '../client/'}),
        (r"/ping.*",
            protocol.PingHandler, {}),

        (r"/bower_components/(.*)",
            tornado.web.StaticFileHandler, {
                'path': os.path.join(
                    package_dir, "..", "client", "bower_components")}),
        (r"/minify/(.*)",
            compile_handlers.MinifyHandler, {
                'path': '/minify/',
                'root': os.path.join(package_dir, "..", "client")}),
        (r"/(.*\.css)",
            compile_handlers.CssHandler, {
                'root': os.path.join(package_dir, "..", "client")}),
        (r"/images/icon-(.*)\.png",
            crud.image.IconHandler, {}),

        (r"/systemconfig.json",
            crud.config.SystemConfigHandler, {}),
        (r"/systemconfig/(.*)",
            crud.config.SystemConfigItemHandler, {}),
        (r"/custom_query/?([^/]*).json",
            crud.custom.CustomQueryHandler, {}),
        (r"/custom_query/?([^/]*)/history.json",
            crud.custom.CustomQueryHistoryHandler, {}),
        (r"/geo/(.*).json",
            crud.org.LocationSearchHandler, {}),

        (r"/surveygroup/?([^/]*).json",
            crud.surveygroup.SurveyGroupHandler, {}),
        (r"/surveygroup/icon/([^/]*)",
            crud.surveygroup.SurveyGroupIconHandler, {}),

        (r"/organisation/?([^/]*).json",
            crud.org.OrgHandler, {}),
        (r"/organisation/?([^/]*)/survey/?([^/]*).json",
            crud.org.PurchasedSurveyHandler, {}),
        (r"/user/?([^/]*).json",
            crud.user.UserHandler, {}),
        (r"/subscription/()([^/]*).json",
            crud.activity.SubscriptionHandler, {}),
        (r"/subscription/([^/]*)/(.*).json",
            crud.activity.SubscriptionHandler, {}),
        (r"/activity/?([^/]*).json",
            crud.activity.ActivityHandler, {}),
        (r"/card.json",
            crud.activity.CardHandler, {}),
        (r"/password.json",
            crud.user.PasswordHandler, {}),

        (r"/program/?([^/]*).json",
            crud.program.ProgramHandler, {}),
        (r"/program/?([^/]*)/history.json",
            crud.program.ProgramTrackingHandler, {}),
        (r"/survey/?([^/]*).json",
            crud.survey.SurveyHandler, {}),
        (r"/survey/?([^/]*)/program.json",
            crud.program.ProgramHistoryHandler, {'mapper': model.Survey}),
        (r"/qnode/?([^/]*).json",
            crud.qnode.QuestionNodeHandler, {}),
        (r"/qnode/?([^/]*)/program.json",
            crud.program.ProgramHistoryHandler, {
                'mapper': model.QuestionNode}),
        (r"/measure/?([^/]*).json",
            crud.measure.MeasureHandler, {}),
        (r"/measure/?([^/]*)/program.json",
            crud.program.ProgramHistoryHandler, {'mapper': model.Measure}),
        (r"/response_type/?([^/]*).json",
            crud.response_type.ResponseTypeHandler, {}),
        (r"/response_type/?([^/]*)/program.json",
            crud.program.ProgramHistoryHandler, {
                'mapper': model.ResponseType}),

        (r"/submission/?([^/]*).json",
            crud.submission.SubmissionHandler, {}),
        (r"/submission/([^/]*)/rnode/?([^/]*).json",
            crud.rnode.ResponseNodeHandler, {}),
        (r"/submission/([^/]*)/response/?([^/]*).json",
            crud.response.ResponseHandler, {}),
        (r"/submission/([^/]*)/response/?([^/]*)/history.json",
            crud.response.ResponseHistoryHandler, {}),
        (r"/submission/([^/]*)/measure/([^/]*)/attachment.json",
            crud.attachment.ResponseAttachmentsHandler, {}),
        (r"/submission/([^/]*)/measure/([^/]*)/submeasure/([^/]*)/attachment.json",
            crud.attachment.ResponseSubmeasureAttachmentsHandler, {}),
        (r"/attachment/([^/]*)(?:/(.*))?",
            crud.attachment.AttachmentHandler, {}),
        (r"/report/sub/stats/program/([^/]*)/survey/([^/]*).json",
            StatisticsHandler, {}),
        (r"/report/diff.json", DiffHandler, {}),
        (r"/report/prog/export/([^/]*)/survey/([^/]*)/([^.]+)\.(.+)",
            ExportProgramHandler, {}),
        (r"/report/exportAssetReport/([^/]*)/survey/([^/]*)/program/([^/]*)/([^.]+)\.(.+)",
            ExportAssetHandler, {}),
        (r"/report/sub/temporal/([^/]*)\.(.+)",
            TemporalReportHandler, {}),
        (r"/report/sub/export/([^/]*)/([^.]+)\.(.+)",
            ExportSubmissionHandler, {}),
        (r"/report/custom_query/reformat\.sql",
            report.custom.SqlFormatHandler, {}),
        (r"/report/custom_query/identifiers\.json",
            report.custom.SqlIdentifierHandler, {}),
        (r"/report/custom_query/preview\.(.+)",
            report.custom.CustomQueryPreviewHandler, {}),
        (r"/report/custom_query/config\.json",
            report.custom.CustomQueryConfigHandler, {}),
        (r"/report/custom_query/([^.]+)/\w+\.(.+)",
            report.custom.CustomQueryReportHandler, {}),

        (r"/import/structure.json",
            ImportStructureHandler, {}),
        (r"/import/submission.json",
            ImportSubmissionHandler, {}),
        (r"/redirect", protocol.RedirectHandler),
        (r"/remap.json", crud.remap.IdMapperHandler),

        # test use session to keep status
        #(r"/status", authn.StatusHandler),
        ########################

        (r"/(.*)", tornado.web.StaticFileHandler, {
            'path': os.path.join(package_dir, "..", "client")}),
    ]


def start_web_server():
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
    max_buffer_size = 10 * 1024**2  # 10MB

    config_dir = os.path.join(get_package_dir(), '..', 'config')
    if os.path.isfile(os.path.join(config_dir, "fullchain.pem")):
        # Some certificate. `fullchain.pem` should contain all the certificates
        # concatenated together:
        # https://docs.python.org/3.4/library/ssl.html#certificate-chains
        ssl_opts = {
            "certfile": os.path.join(config_dir, "fullchain.pem"),
            "keyfile": os.path.join(config_dir, "privkey.pem")
        }
    elif os.path.isdir("/etc/letsencrypt/live/aquamark"):
        # Certificate provided by Let's Encrypt
        ssl_opts = {
            "certfile": "/etc/letsencrypt/live/aquamark/fullchain.pem",
            "keyfile": "/etc/letsencrypt/live/aquamark/privkey.pem"
        }
    else:
        ssl_opts = None

    if ssl_opts is not None:
        logging.getLogger('tornado.general').addFilter(ssl_log_filter)
        # Disable old, vulnerable SSL versions
        # https://blog.qualys.com/ssllabs/2014/10/15/ssl-3-is-dead-killed-by-the-poodle-attack
        ssl_opts['ciphers'] = 'DEFAULT:!SSLv2:!SSLv3:!RC4:!EXPORT:!DES'

    http_server = tornado.httpserver.HTTPServer(
        application, max_body_size=max_buffer_size, ssl_options=ssl_opts)
    http_server.listen(port)

    if log.isEnabledFor(logging.INFO):
        log.info("Tornado version: %s", tornado.version)
        log.debug("Tornado settings: %s", settings)
        log.info(
            "Starting web application. Will be available on port %s", port)
        hostname = socket.gethostname()
        ip = None
        try:
            # Try to get Docker container IP
            with open('/etc/hosts', 'r') as f:
                for line in f:
                    match = re.match(r'^(\S+)\s+%s$' % hostname, line)
                    if match:
                        ip = match.group(1)
                        break
        except OSError:
            pass
        protocol = ssl_opts and 'https' or 'http'
        log.info("Try opening %s://%s:%s", protocol, hostname, port)
        if ip:
            log.info("         or %s://%s:%s", protocol, ip, port)
            log.info("Bound to: %s:%s", ip, port)
    tornado.ioloop.IOLoop.instance().start()


def signal_handler(signum, frame):
    tornado.ioloop.IOLoop.instance().add_callback_from_signal(stop_web_server)


def stop_web_server():
    log.warning("Server shutdown due to signal")
    tornado.ioloop.IOLoop.instance().stop()


def read_app_version():
    package_dir = get_package_dir()
    try:
        with open(os.path.join(package_dir, '..', 'version.txt')) as f:
            version = f.readline().strip()
    except FileNotFoundError:
        version = None
    template.aq_version = version


def configure_http_client():
    if template.aq_version:
        user_agent = "Aquamark %s" % template.aq_version
    else:
        user_agent = "Aquamark"

    tornado.httpclient.AsyncHTTPClient.configure(
        None, defaults=dict(user_agent=user_agent))


if __name__ == "__main__":
    try:
        parse_options()
        connect_db()
        read_app_version()
        configure_http_client()
        signal.signal(signal.SIGTERM, signal_handler)
        start_web_server()
    except KeyboardInterrupt:
        log.info("Shutting down due to user request (e.g. Ctrl-C)")
