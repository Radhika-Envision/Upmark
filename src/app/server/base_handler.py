import logging
from math import ceil
import os
import re

import sqlalchemy
from tornado.escape import json_decode
import tornado.options
import tornado.web

import errors
import model
from utils import denormalise, truthy

log = logging.getLogger('app.base_handler')


class BaseHandler(tornado.web.RequestHandler):

    def prepare(self):
        if (truthy(tornado.options.options.force_https) and
            'X-Forwarded-Proto' in self.request.headers and
            self.request.headers['X-Forwarded-Proto'] != 'https'):
            self.redirect(re.sub(r'^([^:]+)', 'https', self.request.full_url()))

    def get_current_user(self):
        # Cached value is available in current_user property.
        # http://tornado.readthedocs.org/en/latest/web.html#tornado.web.RequestHandler.current_user
        uid = self.get_secure_cookie('user')
        if uid is None:
            return None
        uid = uid.decode('utf8')
        with model.session_scope() as session:
            try:
                user = session.query(model.AppUser).get(uid)
                if user is None:
                    return None
                if user.deleted:
                    superuser = self.get_secure_cookie('superuser')
                    if superuser is None:
                        return None
            except sqlalchemy.exc.StatementError:
                return None
            session.expunge(user)
            return user

    def has_privillege(self, *roles):
        return model.has_privillege(self.current_user.role, *roles)

    def check_privillege(self, *roles):
        if not self.has_privillege(*roles):
            raise errors.AuthzError()

    def check_browse_program(self, session, program_id, survey_id):
        if self.has_privillege('consultant', 'author'):
            return

        n_purchased_surveys = (session.query(model.PurchasedSurvey)
            .filter_by(program_id=program_id,
                       survey_id=survey_id,
                       organisation_id=self.current_user.organisation_id)
            .count())

        if n_purchased_surveys == 0:
            raise errors.AuthzError("This survey has not been purchased yet")

    @property
    def organisation(self):
        if self.current_user is None or self.current_user.organisation_id is None:
            return None
        with model.session_scope() as session:
            organisation = session.query(model.Organisation).\
                get(self.current_user.organisation_id)
            session.expunge(organisation)
            return organisation

    @property
    def request_son(self):
        try:
            return self._request_son
        except AttributeError:
            try:
                self._request_son = denormalise(json_decode(self.request.body))
            except (TypeError, UnicodeError, ValueError) as e:
                raise errors.ModelError(
                    "Could not decode request body: %s. Body started with %s" %
                    (str(e), self.request.body[0:30]))
            return self._request_son

    # Expression to remove invalid characters from headers. Without this,
    # requests may silently fail to be serviced.
    _INVALID_HEADER_CHAR_RE = re.compile(r"[\x00-\x1f\n]")

    def set_status(self, *args, **kwargs):
        reason = kwargs.get('reason')
        if reason:
            reason = BaseHandler._INVALID_HEADER_CHAR_RE.sub('; ', reason)
            kwargs['reason'] = reason
            self.reason(reason)
        return super().set_status(*args, **kwargs)

    def reason(self, message):
        message = BaseHandler._INVALID_HEADER_CHAR_RE.sub('; ', message)
        self.add_header("Operation-Details", message)

    def log_exception(self, typ, value, tb):
        # Print stack trace for InternalModelErrors, since they are very similar
        # to uncaught errors.
        if isinstance(value, errors.InternalModelError):
            log.error(
                "Partially-handled, unexpected error: %s\n%r",
                self._request_summary(), self.request,
                exc_info=(typ, value, tb))
        super().log_exception(typ, value, tb)


class Paginate:
    '''
    Mixin to support pagination.
    '''
    MAX_PAGE_SIZE = 100

    def paginate(self, query, optional=False):
        if optional and self.get_argument("page", None) is None:
            return query

        page_size = self.get_argument("pageSize", str(Paginate.MAX_PAGE_SIZE))
        try:
            page_size = int(page_size)
        except ValueError:
            raise errors.ModelError("Invalid page size")
        if page_size > Paginate.MAX_PAGE_SIZE:
            raise errors.ModelError(
                "Page size is too large (max %d)" % Paginate.MAX_PAGE_SIZE)

        page = self.get_argument("page", "0")
        try:
            page = int(page)
        except ValueError:
            raise errors.ModelError("Invalid page")
        if page < 0:
            raise errors.ModelError("Page must be non-negative")

        num_items = query.count()
        self.set_header('Page-Count', "%d" % ceil(num_items / page_size))
        self.set_header('Page-Index', "%d" % page)
        self.set_header('Page-Item-Count', "%d" % page_size)

        query = query.limit(page_size)
        query = query.offset(page * page_size)
        return query
