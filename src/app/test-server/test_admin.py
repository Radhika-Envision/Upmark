import os
from unittest import mock
import urllib

from sqlalchemy.sql import func
from tornado.escape import json_decode, json_encode
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

import app
import handlers
import model
import user_handlers
from utils import to_dict, simplify, normalise, truthy
import unittest


# TODO: Do this once when the unit tests start up (not in this file?).
app.parse_options()


def get_secure_cookie(user_email=None, super_email=None):
    def _get_secure_cookie(self, name):
        if name == 'user' and user_email is not None:
            with model.session_scope() as session:
                user = session.query(model.AppUser).\
                    filter(func.lower(model.AppUser.email) ==
                           func.lower(user_email)).one()
                return str(user.id).encode('utf8')
        elif name == 'superuser' and super_email is not None:
            with model.session_scope() as session:
                user = session.query(model.AppUser).\
                    filter(func.lower(model.AppUser.email) ==
                           func.lower(super_email)).one()
                return str(user.id).encode('utf8')
        else:
            return None

    return _get_secure_cookie


class OrgStructureTestCase(AsyncHTTPTestCase):

    def create_org_structure(self):
        global user_id
        engine = model.connect_db(os.environ.get('DATABASE_URL'))
        model.Base.metadata.drop_all(engine)
        model.initialise_schema(engine)

        with model.session_scope() as session:
            org1 = model.Organisation(
                name='Primary',
                url='http://primary.org',
                region="Nowhere",
                number_of_customers = 10)
            session.add(org1)
            session.flush()

            org2 = model.Organisation(
                name='Utility',
                url='http://utility.org',
                region="Somewhere",
                number_of_customers = 1000)
            session.add(org2)
            session.flush()

            user = model.AppUser(
                name='Admin', email='admin', role='admin',
                organisation_id=org1.id)
            user.set_password('foo')
            session.add(user)

            user = model.AppUser(
                name='Author', email='author', role='author',
                organisation_id=org1.id)
            user.set_password('bar')
            session.add(user)

            user = model.AppUser(
                name='Authority', email='authority', role='authority',
                organisation_id=org1.id)
            user.set_password('bar')
            session.add(user)

            user = model.AppUser(
                name='Consultant', email='consultant', role='consultant',
                organisation_id=org1.id)
            user.set_password('bar')
            session.add(user)

            user = model.AppUser(
                name='Org Admin', email='org_admin', role='org_admin',
                organisation_id=org2.id)
            user.set_password('bar')
            session.add(user)

            user = model.AppUser(
                name='Clerk', email='clerk', role='clerk',
                organisation_id=org2.id)
            user.set_password('bar')
            session.add(user)

    def setUp(self):
        super().setUp()
        self.create_org_structure()

    def get_app(self):
        return Application(app.get_mappings(), **app.get_minimal_settings())


class AuthNTest(OrgStructureTestCase):

    def test_unauthenticated_root(self):
        response = self.fetch("/", follow_redirects=True)
        self.assertIn("/login/", response.effective_url)

    def test_login(self):
        post_data = {
            'email': 'admin',
            'password': 'bar'
        }
        response = self.fetch(
            "/login", follow_redirects=False, method='POST',
            body=urllib.parse.urlencode(post_data))
        self.assertEqual(302, response.code)
        self.assertIn('user=;', response.headers['set-cookie'])
        self.assertIn('superuser=;', response.headers['set-cookie'])

        post_data['password'] = 'foo'
        response = self.fetch(
            "/login", follow_redirects=False, method='POST',
            body=urllib.parse.urlencode(post_data))
        self.assertEqual(302, response.code)
        self.assertIn('user=', response.headers['set-cookie'])

    @mock.patch('tornado.web.RequestHandler.get_secure_cookie',
                get_secure_cookie(user_email='admin'))
    def test_authenticated_root(self):
        response = self.fetch("/")
        self.assertIn("Sign out", response.body.decode('utf8'))


class OrgAuthzTest(OrgStructureTestCase):

    def test_create_org(self):
        users = [
            ('clerk', 403, 'Not authorised'),
            ('org_admin', 403, 'Not authorised'),
            ('consultant', 403, 'Not authorised'),
            ('authority', 403, 'Not authorised'),
            ('author', 403, 'Not authorised'),
            ('admin', 200, 'OK')
        ]

        for i, (user, code, reason) in enumerate(users):
            post_data = {
                "name": "Foo %d" % i,
                "url": "http://foo%d.com" % i,
                "numberOfCustomers": 0,
                "region": "Foo"
            }
            with mock.patch('tornado.web.RequestHandler.get_secure_cookie',
                    get_secure_cookie(user_email=user)):
                response = self.fetch(
                    "/organisation.json", method='POST',
                    body=json_encode(post_data))
                self.assertEqual(reason, response.reason)
                self.assertEqual(code, response.code)

    def test_modify_org(self):
        users_own = [
            ('clerk', 'Utility', 403, 'Not authorised'),
            ('org_admin', 'Utility', 200, 'OK'),
            ('consultant', 'Primary', 403, 'Not authorised'),
            ('authority', 'Primary', 403, 'Not authorised'),
            ('author', 'Primary', 403, 'Not authorised'),
            ('admin', 'Primary', 200, 'OK')
        ]
        for user, org_name, code, reason in users_own:
            self.modify_org(user, org_name, code, reason)

        users_other = [
            ('clerk', 'Primary', 403, 'Not authorised'),
            ('org_admin', 'Primary', 403, "can't modify another organisation"),
            ('consultant', 'Utility', 403, 'Not authorised'),
            ('authority', 'Utility', 403, 'Not authorised'),
            ('author', 'Utility', 403, 'Not authorised'),
            ('admin', 'Utility', 200, 'OK')
        ]
        for user, org_name, code, reason in users_other:
            self.modify_org(user, org_name, code, reason)


    def modify_org(self, user_email, org_name, code, reason):
        with model.session_scope() as session:
            org = session.query(model.Organisation).\
                filter(func.lower(model.Organisation.name) ==
                       func.lower(org_name)).one()
            session.expunge(org)

        org_son = to_dict(org, include={'id', 'name'})
        org_son = simplify(org_son)
        org_son = normalise(org_son)

        with mock.patch('tornado.web.RequestHandler.get_secure_cookie',
                get_secure_cookie(user_email=user_email)):

            post_data = org_son.copy()
            response = self.fetch(
                "/organisation/%s.json" % org.id, method='PUT',
                body=json_encode(post_data))
        self.assertIn(reason, response.reason)
        self.assertEqual(code, response.code)


class UserAuthzTest(OrgStructureTestCase):

    def test_modify_user(self):
        with model.session_scope() as session:
            # TODO: Refactor this to make it reusable.
            user = session.query(model.AppUser).\
                filter(func.lower(model.AppUser.email) ==
                       func.lower('clerk')).one()
            org_son = to_dict(user.organisation, include={'id'})
            org_son = simplify(org_son)
            org_son = normalise(org_son)
            user_son = to_dict(user, exclude={'password'})
            user_son = simplify(user_son)
            user_son = normalise(user_son)
            user_son["organisation"] = org_son

            org = session.query(model.Organisation).\
                filter_by(name='Primary').one()
            org1_id = str(org.id)
            org = session.query(model.Organisation).\
                filter_by(name='Utility').one()
            org2_id = str(org.id)

        users = [
            ('consultant', 403, "can't modify another user"),
            ('authority', 403, "can't modify another user"),
            ('author', 403, "can't modify another user"),
            ('clerk', 200, 'OK'),
            ('org_admin', 200, 'OK'),
            ('admin', 200, 'OK')
        ]

        for user_email, code, reason in users:
            post_data = user_son.copy()
            post_data['organisation'] = post_data['organisation'].copy()
            with mock.patch('tornado.web.RequestHandler.get_secure_cookie',
                    get_secure_cookie(user_email=user_email)):
                response = self.fetch(
                    "/user/%s.json" % user_son['id'], method='PUT',
                    body=json_encode(post_data))
                self.assertIn(reason, response.reason, msg=user_email)
                self.assertEqual(code, response.code)

        users = [
            ('clerk', 403, "can't enable or disable yourself"),
            ('org_admin', 200, 'OK'),
        ]

        for user_email, code, reason in users:
            post_data = user_son.copy()
            post_data['organisation'] = post_data['organisation'].copy()
            post_data['enabled'] = False
            with mock.patch('tornado.web.RequestHandler.get_secure_cookie',
                    get_secure_cookie(user_email=user_email)):
                response = self.fetch(
                    "/user/%s.json" % user_son['id'], method='PUT',
                    body=json_encode(post_data))
                self.assertIn(reason, response.reason, msg=user_email)
                self.assertEqual(code, response.code)


class SurveyTest(OrgStructureTestCase):

    def test_create_survey(self):
        with mock.patch('tornado.web.RequestHandler.get_secure_cookie',
                    get_secure_cookie(user_email='admin')):
                post_data = {
                    'title': 'test'
                }
                response = self.fetch(
                    "/survey.json", method='POST',
                    body=json_encode(post_data))
                self.assertEqual("OK", response.reason)
                self.assertEqual(200, response.code)
