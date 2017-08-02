# Copyright VPAC Innovations Pty Ltd
# Copied from Landblade


import base64
import inspect
import logging
import os

import tornado.options


log = logging.getLogger('app.cache_bust')


def get_package_dir():
    frameinfo = inspect.getframeinfo(inspect.currentframe())
    return os.path.dirname(frameinfo.filename)


def factory():
    if tornado.options.options.dev:
        return DevVersion()
    else:
        return ReleaseVersion()


semi_volatile_stamp = None


class Version:
    def __init__(self):
        self.volatile_stamp = random_stamp()

    def get(self, mode):
        '''
        @param mode: The versioning mode to use {'v', 'nv', 'sv'}
        '''
        if mode in {'vv', 'super-volatile'}:
            # Literal value; will be processed later
            return 'vv'
        elif mode in {'v', 'volatile'}:
            # Always change
            return 'v_%s' % self.volatile_stamp
        elif mode in {'nv', 'non-volatile'}:
            # Never change; non-volatile
            return 'nv'
        else:
            # Change on deployment ('sv', 'semi-volatile')
            return 'sv_%s' % semi_volatile_stamp


class DevVersion(Version):
    def __call__(self, rel, dev):
        '''
        @param rel: The versioning mode to use in release mode (ignored)
        @param dev: The versioning mode to use in dev mode
        '''
        return super().get(dev)


class ReleaseVersion(Version):
    def __call__(self, rel, dev):
        '''
        @param rel: The versioning mode to use in release mode
        @param dev: The versioning mode to use in dev mode (ignored)
        '''
        return super().get(rel)


def random_stamp():
    '''
    @return a random string that can be used as a variable and in a URL
    '''
    stamp = base64.b32encode(os.urandom(6)).decode('ascii')
    return stamp.replace('=', ' ').strip()


if __name__ == '__main__':
    print(random_stamp())
else:
    try:
        # BUILD_TIME.txt should be created by build process. It contains a
        # version string that is unique to this build.
        metadata_path = os.path.join(get_package_dir(), '..', 'BUILD_TIME.txt')
        with open(metadata_path) as f:
            semi_volatile_stamp = f.readline().strip()
    except IOError as e:
        log.warning(
            "Could not open BUILD_TIME.txt: %s. "
            "Generating temporary stamp.", e)
        semi_volatile_stamp = random_stamp()
