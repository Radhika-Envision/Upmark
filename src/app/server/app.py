#!/usr/bin/env python3

import inspect
import logging.config
import os

import tornado.options
import tornado.web

#import data
import handlers


log = logging.getLogger('app')

tornado.options.options.logging = 'none'

def get_package_dir():
    frameinfo = inspect.getframeinfo(inspect.currentframe())
    return os.path.dirname(frameinfo.filename)


def read_config():
    # Logging configuration
    package_dir = get_package_dir()

    port = os.environ.get('PORT')
    if port is None:
        port = 8000
    tornado.options.define("port", default=port,
                           help="Bind to this port", type=int)

    logconf_path = os.path.join(package_dir, 'logging.cfg')
    if not os.path.exists(logconf_path):
        log.info("Warning: log config file %s does not exist.", logconf_path)
    else:
        logging.config.fileConfig(logconf_path)

    dev = os.environ.get('DEV_MODE')
    if dev is None:
        dev = 'True'
    tornado.options.define("dev", default=dev,
                           help="Development mode (default: True)")

    analytics_id = os.environ.get('ANALYTICS_ID')
    if analytics_id is None:
        analytics_id = ''
    tornado.options.define("analytics_id", default=analytics_id,
                           help="Google Analytics ID (default: '')")

    tornado.options.parse_command_line()


def start_web_server():

    package_dir = get_package_dir()

    settings = {
        #"cookie_secret": os.environ.get('COOKIE_SECRET'),
        "cookie_secret": "this_is_the_secret_for_cookie",
        "debug": True,
        "gzip": True,
        "template_path": os.path.join(package_dir, "..", "client"),
        "login_url": "/login/",
    }

    application = tornado.web.Application(
        [
            (r"/login/", handlers.AuthLoginHandler, {
                'path': os.path.join(package_dir, "..", "client")}),
            (r"/logout/", handlers.AuthLogoutHandler),
            (r"/()", handlers.MainHandler, {
                'path': '../client/index.html'}),
            (r"/bower_components/(.*)", tornado.web.StaticFileHandler, {
                'path': os.path.join(package_dir, "..", ".bower_components")}),
            (r"/minify/(.*)", handlers.MinifyHandler, {
                'path': '/minify/', 'root': os.path.join(package_dir, "..", "client")}),
            (r"/(.*\.css)", handlers.CssHandler, {
                'root': os.path.join(package_dir, "..", "client")}),
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
        log.info(
            "Starting web application. Will be available on port %s", port)
        log.info("Try opening http://%s:%s", socket.gethostname(), port)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
    try:
        read_config()
    except Exception as e:
        raise e
#    try:
#        data.connect()
#    except Exception as e:
#        raise e
    try:
        start_web_server()
    except KeyboardInterrupt:
        log.info("Shutting down due to user request (e.g. Ctrl-C)")
