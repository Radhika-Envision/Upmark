from concurrent.futures import ThreadPoolExecutor

from tornado import gen
from tornado.concurrent import run_on_executor

import config
import handlers
import image
import model


class IconHandler(handlers.BaseHandler):

    executor = ThreadPoolExecutor(max_workers=1)

    @gen.coroutine
    def get(self, size):
        size = int(size)

        if size < 8:
            raise handlers.MissingDocError("Size is too small")
        if size > 256:
            raise handlers.MissingDocError("Size is too big")

        if size <= 64:
            name = 'icon_sm'
        else:
            name = 'icon_lg'

        with model.session_scope() as session:
            data = yield self.get_icon(session, name, size)

        self.set_header('Content-Type', 'image/png')
        self.write(data)
        self.finish()

    @run_on_executor
    def get_icon(self, session, name, size):
        return image.get_icon(session, name, size)


class SvgHandler(handlers.BaseHandler):

    executor = ThreadPoolExecutor(max_workers=1)

    def initialize(self, name):
        self.name = name

    @gen.coroutine
    def get(self):
        with model.session_scope() as session:
            data = yield self.get_svg(session, self.name)

        self.set_header('Content-Type', 'image/svg+xml')
        self.write(data)
        self.finish()

    @run_on_executor
    def get_svg(self, session, name):
        image.check_display(name)
        data = config.get_setting(session, name)
        return image.clean_svg(data).encode('utf-8')
