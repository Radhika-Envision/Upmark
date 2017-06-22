import logging
import os

from expiringdict import ExpiringDict
import sass
import tornado.options
import tornado.web

import config
import errors
from utils import falsy

log = logging.getLogger('app.compile')


class RamCacheHandler(tornado.web.RequestHandler):

    cache = ExpiringDict(max_len=100, max_age_seconds=10)

    def get(self, path):
        if path in RamCacheHandler.cache and falsy(tornado.options.options.dev):
            self.write_from_cache(path)
        else:
            log.debug('Generating %s', path)
            mimetype, text = self.generate(path)
            self.add_to_cache(path, mimetype, text)
            self.write_from_cache(path)

    def generate(self, path):
        raise tornado.web.HTTPError(
            404, "Path %s not found in cache.", path)

    def add_to_cache(self, path, mimetype, text):
        RamCacheHandler.cache[path] = {
            'mimetype': mimetype,
            'text': text
        }

    def write_from_cache(self, path):
        entry = RamCacheHandler.cache[path]
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

    def generate(self, path):
        path = self.path + path
        bower_versions = config.bower_versions()

        decls = config.get_resource('js_manifest')
        decls = config.deep_interpolate(decls, bower_versions)
        for decl in decls:
            if 'min-href' in decl and decl['min-href'] == path:
                return 'text/javascript', self.minify_js(decl)

        decls = config.get_resource('css_manifest')
        decls = config.deep_interpolate(decls, bower_versions)
        for decl in decls:
            if 'min-href' in decl and decl['min-href'] == path:
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
        for source in sources:
            if source.startswith('/'):
                source = os.path.join(self.root, source[1:])
            else:
                source = os.path.join(self.root, source)
            source = resolve_file(source, extension_map={'.css': ['.scss']})
            text += sass.compile(filename=source, output_style='compressed')
            text += "\n"
        return text

    def read_all(self, sources, extension_map=None):
        text = ""
        for source in sources:
            if source.startswith('/'):
                source = os.path.join(self.root, source[1:])
            else:
                source = os.path.join(self.root, source)
            source = resolve_file(source, extension_map)
            source = os.path.abspath(source)
            if not source.startswith(self.root):
                raise errors.InternalModelError(
                    "Resource configuration is invalid",
                    log_message="%s is not in %s" % (source, self.root))
            with open(source, 'r', encoding='utf8') as f:
                text += f.read()
            text += "\n"
        return text


class CssHandler(RamCacheHandler):
    '''
    Converts funky CSS formats to regular CSS. This is generally used in
    non-minification mode; the MinifyHandler also compiles SASS.
    '''

    def initialize(self, root):
        self.root = root

    def generate(self, path):
        log.debug("Compiling CSS for %s", path)
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
