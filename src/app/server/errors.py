import logging
import re

import tornado.web


log = logging.getLogger('app.errors')

class AuthzError(tornado.web.HTTPError):
    '''
    The user tried to do something they're not allowed to.
    '''
    def __init__(self, reason="Not authorised", log_message=None, *args, **kwargs):
        tornado.web.HTTPError.__init__(
            self, 403, reason=reason, log_message=log_message, *args, **kwargs)


class ModelError(tornado.web.HTTPError):
    '''
    The user's input doesn't conform to the API spec.
    '''
    def __init__(self, reason="Arguments are invalid", log_message=None, *args, **kwargs):
        tornado.web.HTTPError.__init__(
            self, 403, reason=reason, log_message=log_message, *args, **kwargs)

    POSTGRES_PATTERN = re.compile(r'\([^)]+\) (.*)')

    @classmethod
    def from_sa(cls, sa_error, reason="Arguments are invalid: "):
        log.error('%s', str(sa_error))
        match = cls.POSTGRES_PATTERN.search(str(sa_error))
        if match is not None:
            return cls(reason="%s%s" % (reason, match.group(1)))
        else:
            return cls(reason=reason)

    @classmethod
    def from_voluptuous(cls, v_error, reason="Arguments are invalid: "):
        log.error('%s', str(v_error))
        if v_error.error_message:
            return cls(reason=v_error.error_message)
        else:
            return cls(reason=str(v_error))


class MissingDocError(tornado.web.HTTPError):
    def __init__(self, reason="Document not found", log_message=None, *args, **kwargs):
        tornado.web.HTTPError.__init__(
            self, 404, reason=reason, log_message=log_message, *args, **kwargs)


class MethodError(tornado.web.HTTPError):
    def __init__(self, reason="Method not allowed", log_message=None, *args, **kwargs):
        tornado.web.HTTPError.__init__(
            self, 405, reason=reason, log_message=log_message, *args, **kwargs)


class InternalModelError(tornado.web.HTTPError):
    '''
    Unexpected error. Throw one of these if you don't know *why* the
    exception occurred, but you want to add a message to explain *where* it
    happened.
    '''
    def __init__(self, reason="Bug in data model", log_message=None, *args, **kwargs):
        tornado.web.HTTPError.__init__(
            self, 500, reason=reason, log_message=log_message, *args, **kwargs)
