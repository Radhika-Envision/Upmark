from concurrent.futures import ThreadPoolExecutor
import logging
import os

import cairosvg
from tornado import gen
from tornado.concurrent import run_on_executor
from tornado.escape import json_decode, json_encode
import tornado.web
from scour import scour
import sqlalchemy

import handlers
import model
import crud.config
from utils import get_package_dir, to_camel_case, to_snake_case, ToSon


log = logging.getLogger('app.logo')


def clean_svg(svg):
    '''
    Clean up an SVG file.
    - Remove script tags and the like
    - Reduce file size
    '''
    opts = scour.parse_args(args=[
        '--disable-group-collapsing',
        '--enable-viewboxing',
        '--enable-id-stripping',
        '--enable-comment-stripping',
        '--indent=none',
        '--protect-ids-noninkscape',
        '--quiet',
        '--remove-metadata',
        '--set-precision=5',
    ])[0]
    output = scour.scourString(svg, opts)
    return output


def get_icon(session, name, size):
    check_display(name)
    data = crud.config.get_setting(session, name)
    bitmap = cairosvg.svg2png(data,parent_width=size, parent_height=size)
    return bitmap


def check_display(name):
    schema = crud.config.SCHEMA.get(name)
    if not schema:
        raise handlers.MissingDocError("No such icon")
    if crud.config.is_private(name, schema):
        raise handlers.MissingDocError("No such icon")
    if schema['type'] != 'image':
        raise handlers.MissingDocError("No such icon")


class IconHandler(handlers.BaseHandler):

    executor = ThreadPoolExecutor(max_workers=1)

    def get(self, size):
        size = int(size)

        if size < 8:
            raise handlers.MissingDocError("Size is too small")
        if size > 256:
            raise handlers.MissingDocError("Size is too big")

        if size <= 64:
            name = 'logo_monogram_small'
        else:
            name = 'logo_monogram_big'

        with model.session_scope() as session:
            data = get_icon(session, name, size)

        self.set_header('Content-Type', 'image/png')
        self.write(data)
        self.finish()

    @run_on_executor
    def minify_svg(self):
        pass
