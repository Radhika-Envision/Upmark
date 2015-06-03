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

class BaseHandler(tornado.web.RequestHandler):

    def get_login_url(self):
        return u"/login"

    def get_current_user(self):
        user_json = self.get_secure_cookie("user")
        if user_json:
            return tornado.escape.json_decode(user_json)
        else:
            return None

class AuthLogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie("user")
        self.redirect(self.get_argument("next", "/"))

class AuthLoginHandler(BaseHandler):
    def get(self):
        try:
            errormessage = self.get_argument("error")
        except:
            errormessage = ""
        self.render("../client/login.html", errormessage = errormessage)

    def check_permission(self, password, username):
        if username == "admin" and password == "admin":
            return True
        return False

    def post(self):
        username = self.get_argument("username", "")
        password = self.get_argument("password", "")
        auth = self.check_permission(password, username)
        if auth:
            self.set_current_user(username)
            self.redirect(self.get_argument("next", u"/"))
        else:
            error_msg = u"?error=" + tornado.escape.url_escape("Login incorrect")
            self.redirect(u"/auth/login/" + error_msg)

    def set_current_user(self, user):
        if user:
            self.set_secure_cookie("user", tornado.escape.json_encode(user))
        else:
            self.clear_cookie("user")

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
        "cookie_secret": os.environ.get('COOKIE_SECRET'),
        "debug": True,
        "gzip": True,
        "template_path": os.path.join(package_dir, "..", "client")
    }

    application = tornado.web.Application(
        [
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
            (r"/auth/login/", AuthLoginHandler, {
                'path': '../client/login.html'}),
            (r"/auth/logout/", AuthLogoutHandler),
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
