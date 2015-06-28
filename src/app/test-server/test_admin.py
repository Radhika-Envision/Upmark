import os
from unittest import mock

from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

import app
import handlers
import model
import user_handlers


# TODO: Do this once when the unit tests start up.
app.parse_options()

user_id = None
superuser = None


def get_secure_cookie(self, name):
    if name == 'user' and user_id is not None:
        return user_id.encode('utf8')
    elif name == 'superuser' and superuser_id is not None:
        return superuser_id.encode('utf8')
    else:
        return None


class AuthNTest(AsyncHTTPTestCase):

    def setUp(self):
        global user_id
        super().setUp()
        engine = model.connect_db(os.environ.get('DATABASE_URL'))
        model.Base.metadata.drop_all(engine)
        model.initialise_schema(engine)

        with model.session_scope() as session:
            org = model.Organisation(
                name='Test Org',
                url='http://test.org',
                region="Nowhere",
                number_of_customers = 0)
            session.add(org)
            session.flush()
            user = model.AppUser(
                name='Fred', email='f@f', role='admin', organisation_id=org.id)
            user.set_password('')
            session.add(user)
            session.flush()
            user_id = str(user.id)

    def get_app(self):
        return Application(app.get_mappings(), **app.get_minimal_settings())

    def test_unauth(self):
        response = self.fetch("/")
        self.assertIn("form-signin", response.body.decode('utf8'))

    @mock.patch('tornado.web.RequestHandler.get_secure_cookie',
                get_secure_cookie)
    def test_auth(self):
        response = self.fetch("/")
        self.assertIn("Sign out", response.body.decode('utf8'))
