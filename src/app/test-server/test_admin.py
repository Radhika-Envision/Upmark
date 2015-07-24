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
        app.default_settings()

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


class OrgTest(OrgStructureTestCase):

    def test_list_org(self):
        with mock.patch('tornado.web.RequestHandler.get_secure_cookie',
                get_secure_cookie(user_email='admin')):
            response = self.fetch(
                "/organisation.json", method='GET',)

        orgs_son = json_decode(response.body)
        self.assertIsInstance(orgs_son, list)
        self.assertEqual(len(orgs_son), 2)
        del orgs_son[0]['id']
        del orgs_son[1]['id']
        expected = [
            {
                'numberOfCustomers': 10,
                'name': 'Primary',
                'region': 'Nowhere'
            }, {
                'numberOfCustomers': 1000,
                'name': 'Utility',
                'region': 'Somewhere'
            }
        ]
        self.assertEqual(orgs_son, expected)


class UserTest(OrgStructureTestCase):

    def test_list_org(self):
        with mock.patch('tornado.web.RequestHandler.get_secure_cookie',
                get_secure_cookie(user_email='admin')):
            response = self.fetch(
                "/user.json?pageSize=2&page=0", method='GET',)

        orgs_son = json_decode(response.body)
        self.assertIsInstance(orgs_son, list)
        self.assertEqual(len(orgs_son), 2)
        del orgs_son[0]['id']
        del orgs_son[0]['organisation']['id']
        del orgs_son[1]['id']
        del orgs_son[1]['organisation']['id']
        expected = [
            {
                'name': 'Admin',
                'enabled': True,
                'organisation': {
                    'name': 'Primary'
                }
            }, {
                'name': 'Author',
                'enabled': True,
                'organisation': {
                    'name': 'Primary'
                }
            }
        ]
        self.assertEqual(orgs_son, expected)


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

    def test_create_user(self):
        users_own = [
            ('clerk', 'Utility', 403, "You can't create a new user."),
            ('org_admin', 'Utility', 200, 'OK'),
            ('consultant', 'Primary', 403, "You can't create a new user."),
            ('authority', 'Primary', 403, "You can't create a new user."),
            ('author', 'Primary', 403, "You can't create a new user."),
            ('admin', 'Primary', 200, 'OK')
        ]

        for i, (user_email, org_name, code, reason) in enumerate(users_own):
            self.create_user(i, 'own', user_email, org_name, 'clerk', code, reason)

        users_other = [
            ('clerk', 'Primary', 403, "You can't create a new user."),
            ('org_admin', 'Primary', 403, "You can't create/modify another organisation's user."),
            ('consultant', 'Utility', 403, "You can't create a new user."),
            ('authority', 'Utility', 403, "You can't create a new user."),
            ('author', 'Utility', 403, "You can't create a new user."),
            ('admin', 'Utility', 200, 'OK')
        ]

        for i, (user_email, org_name, code, reason) in enumerate(users_own):
            self.create_user(i, 'other', user_email, org_name, 'clerk', code, reason)

    def test_create_user_role(self):
        admin_role = [
            ('admin', 'clerk', 'Primary', 200, 'OK'),
            ('admin', 'org_admin', 'Primary', 200, 'OK'),
            ('admin', 'consultant', 'Primary', 200, 'OK'),
            ('admin', 'authority', 'Primary', 200, 'OK'),
            ('admin', 'author', 'Primary', 200, 'OK'),
            ('admin', 'admin', 'Primary', 200, 'OK')
        ]

        for i, (user_email, role, org_name, code, reason) in enumerate(admin_role):
            self.create_user(i, 'admin', user_email, org_name, role, code, reason)

        org_admin_role = [
            ('org_admin', 'clerk', 'Utility', 200, 'OK'),
            ('org_admin', 'org_admin', 'Utility', 200, 'OK'),
            ('org_admin', 'consultant', 'Utility', 403, "You can't set this role."),
            ('org_admin', 'authority', 'Utility', 403, "You can't set this role."),
            ('org_admin', 'author', 'Utility', 403, "You can't set this role."),
            ('org_admin', 'admin', 'Utility', 403, "You can't set this role.")
        ]

        for i, (user_email, role, org_name, code, reason) in enumerate(org_admin_role):
            self.create_user(i, 'org_admin', user_email, org_name, role, code, reason)

    def create_user(self, prefix, i, user_email, org_name, role, code, reason):
        with model.session_scope() as session:
            org = session.query(model.Organisation).\
                filter(func.lower(model.Organisation.name) ==
                       func.lower(org_name)).one()
            session.expunge(org)

        post_data = {
            'email': 'user%s%s' % (prefix, i),
            'name': 'foo',
            'password': 'bar',
            'role': role,
            'organisation': {'id': str(org.id)}
        }

        with mock.patch('tornado.web.RequestHandler.get_secure_cookie',
                        get_secure_cookie(user_email=user_email)), \
                mock.patch('crud.user.test_password', lambda x: (1.0, 0.1, {})):
            response = self.fetch(
                "/user.json", method='POST',
                body=json_encode(post_data))
            self.assertIn(reason, response.reason, msg=user_email)
            self.assertEqual(code, response.code)

    def test_set_password(self):
        with model.session_scope() as session:
            org = session.query(model.Organisation).\
                filter(func.lower(model.Organisation.name) ==
                       func.lower('utility')).one()
            session.expunge(org)

        post_data = {
            'email': 'passwordTest',
            'name': 'ptest',
            'password': 'bar',
            'role': 'clerk',
            'organisation': {'id': str(org.id)}
        }

        with mock.patch('tornado.web.RequestHandler.get_secure_cookie',
                        get_secure_cookie(user_email='admin')):
            response = self.fetch(
                "/user.json", method='POST',
                body=json_encode(post_data))
            self.assertIn('not strong enough', response.reason)
            self.assertEqual(403, response.code)

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

    def test_modify_org_in_user(self):
        users = [
            ('clerk', 'Utility', 'Primary', 403, "You can't change your organisation."),
            ('org_admin', 'Utility', 'Primary', 403, "You can't create/modify another organisation's user."),
            ('consultant', 'Primary', 'Utility', 403, "You can't change your organisation."),
            ('authority', 'Primary', 'Utility', 403, "You can't change your organisation."),
            ('author', 'Primary', 'Utility', 403, "You can't change your organisation."),
            ('admin', 'Primary', 'Utility', 200, 'OK')
        ]

        for user_email, current_org_name, new_org_name, code, reason in users:
            self.modify_org_in_user(user_email, current_org_name, new_org_name, code, reason)

    def modify_org_in_user(self, user_email, old_org_name, new_org_name, code, reason):
        with model.session_scope() as session:
            org = session.query(model.Organisation).\
                filter(func.lower(model.Organisation.name) ==
                       func.lower(new_org_name)).one()
            org_son = to_dict(org, include={'id', 'name'})
            org_son = simplify(org_son)
            org_son = normalise(org_son)

            user = session.query(model.AppUser).\
                    filter(func.lower(model.AppUser.email) ==
                           func.lower(user_email)).one()
            user_son = to_dict(user, exclude={'password'})
            user_son = simplify(user_son)
            user_son = normalise(user_son)
            user_son['organisation'] = org_son
            post_data = user_son.copy()

            with mock.patch('tornado.web.RequestHandler.get_secure_cookie',
                    get_secure_cookie(user_email=user_email)):
                response = self.fetch(
                    "/user/%s.json" % user_son['id'], method='PUT',
                    body=json_encode(post_data))
                self.assertIn(reason, response.reason, msg=user_email)
                self.assertEqual(code, response.code)


class PasswordTest(OrgStructureTestCase):

    def test_password_strength(self):
        response = self.fetch(
            "/password.json", method='POST',
            body=json_encode({'password': 'foo'}))
        self.assertEqual(200, response.code)
        son = json_decode(response.body)
        self.assertLess(son['strength'], 0.5)
        self.assertIn('charmix', son['improvements'])
        self.assertIn('length', son['improvements'])

        response = self.fetch(
            "/password.json", method='POST',
            body=json_encode({'password': 'f0!'}))
        self.assertEqual(200, response.code)
        son = json_decode(response.body)
        self.assertNotIn('charmix', son['improvements'])
        self.assertIn('length', son['improvements'])

        response = self.fetch(
            "/password.json", method='POST',
            body=json_encode({'password': 'fooooooooooooooooooooooo'}))
        self.assertEqual(200, response.code)
        son = json_decode(response.body)
        self.assertIn('charmix', son['improvements'])
        self.assertNotIn('length', son['improvements'])

        response = self.fetch(
            "/password.json", method='POST',
            body=json_encode({'password': 'bdFiuo2807 g97834tq !'}))
        self.assertEqual(200, response.code)
        son = json_decode(response.body)
        self.assertGreater(son['strength'], 0.9)
        self.assertNotIn('length', son['improvements'])
        self.assertNotIn('charmix', son['improvements'])
