import logging
from math import ceil
import re

from expiringdict import ExpiringDict
import sqlalchemy.exc
from sqlalchemy.orm import joinedload
from tornado.escape import json_decode
import tornado.options
import tornado.web

import errors
import model
from session import UserSession
from utils import denormalise, truthy

log = logging.getLogger('app.base_handler')


cache = ExpiringDict(max_len=100, max_age_seconds=10)


class BaseHandler(tornado.web.RequestHandler):

    root_policy = None

    def prepare(self):
        if (truthy(tornado.options.options.force_https) and
                'X-Forwarded-Proto' in self.request.headers and
                self.request.headers['X-Forwarded-Proto'] != 'https'):
            # Redirect from HTTP to HTTPS when behind a load balancer on AWS.
            # http://docs.aws.amazon.com/elasticloadbalancing/latest/classic/x-forwarded-headers.html#x-forwarded-proto
            self.redirect(
                re.sub(r'^([^:]+)', 'https', self.request.full_url()))
            return

    def get_current_user(self):
        with model.session_scope() as session:
            return self.get_user_session(session)

    USER_IDS_PATTERN = re.compile(r'^user=([-\w]*)(?:, ?superuser=([-\w]*))?$')

    def get_user_session(self, db_session):
        # TODO: Currently, this is done twice: once for authentication, and
        # again for authorisation. Because the database session is closed in
        # get_current_user, the user session object can't be used in the
        # request handler methods. Is there some way to do it without closing
        # the session?
        user_ids = self.get_secure_cookie('user')
        if not user_ids:
            return None
        user_ids = user_ids.decode('utf8')

        match = self.USER_IDS_PATTERN.match(user_ids)
        if not match:
            return None
        user_id, superuser_id = match.groups()

        if not user_id:
            return None

        if superuser_id:
            superuser = (
                db_session.query(model.AppUser)
                .options(joinedload('organisation'))
                .options(joinedload('surveygroups'))
                .get(superuser_id))
            if not superuser:
                # True user's session has expired.
                return None
            if superuser.deleted or superuser.organisation.deleted:
                raise errors.AuthzError("Your account has been disabled")
        else:
            superuser = None

        user = (
            db_session.query(model.AppUser)
            .options(joinedload('organisation'))
            .options(joinedload('surveygroups'))
            .get(user_id))
        if not user:
            return None
        if user.deleted or user.organisation.deleted:
            raise errors.AuthzError("Your account has been disabled")

        # When impersonating, make sure the user is still under the superuser's
        # jurisdiction.
        user_session = UserSession(user, superuser)
        if superuser and superuser != user:
            policy = user_session.policy.derive({
                'user': user,
                'surveygroups': user.surveygroups,
            })
            policy.verify('user_impersonate')

        return user_session

    @property
    def request_son(self):
        try:
            return self._request_son
        except AttributeError:
            pass
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
        # Print stack trace for InternalModelErrors, since they are very
        # similar to uncaught errors.
        if isinstance(value, errors.InternalModelError):
            log.error(
                "Partially-handled, unexpected error: %s\n%r",
                self._request_summary(), self.request,
                exc_info=(typ, value, tb))
        super().log_exception(typ, value, tb)

    def send_error(self, status_code=500, exc_info=None, **kwargs):
        if not self._headers_written and exc_info:
            exc_cls, e, trace = exc_info
            if isinstance(e, sqlalchemy.exc.SQLAlchemyError):
                try:
                    if self.handle_sa_exception(e):
                        return
                except Exception:
                    log.error(
                        "Uncaught exception in handle_sa_exception",
                        exc_info=True)

        super().send_error(
            status_code=status_code, exc_info=exc_info, **kwargs)

    INTEGRITY_PATTERN = re.compile(
        r'duplicate key.*?"(\w+)".*?DETAIL:\s+Key (.*?) already exists.')

    def handle_sa_exception(self, e):
        if isinstance(e, sqlalchemy.exc.IntegrityError):
            match = self.INTEGRITY_PATTERN.search(str(e).replace('\n', ''))
            if not match:
                return False
            if match.group(1) in errors.integrity_error_lut:
                reason = errors.integrity_error_lut.get(match.group(1))
            else:
                reason = "Another entity already has that value: {}".format(
                    match.group(2))
            self.set_status(400, reason=reason)
        else:
            return False

        try:
            self.write_error(400)
        except Exception:
            log.error("Uncaught exception in write_error", exc_info=True)
        return True


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

        query.distinct()

        num_items = query.count()
        self.set_header('Page-Count', "%d" % ceil(num_items / page_size))
        self.set_header('Page-Index', "%d" % page)
        self.set_header('Page-Item-Count', "%d" % page_size)

        query = query.limit(page_size)
        query = query.offset(page * page_size)
        return query
