import os
import unittest
from unittest import mock
import urllib

from sqlalchemy.sql import func
from tornado.escape import json_decode, json_encode

import app
import base
import model
from utils import ToSon


class AuthNTest(base.AqHttpTestBase):

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

    def test_authenticated_root(self):
        with base.mock_user('admin'):
            response = self.fetch("/")
        self.assertIn("Sign out", response.body.decode('utf8'))


class OrgTest(base.AqHttpTestBase):

    def test_list_org(self):
        with base.mock_user('admin'):
            response = self.fetch(
                "/organisation.json", method='GET',)

        orgs_son = json_decode(response.body)
        self.assertIsInstance(orgs_son, list)
        self.assertEqual(len(orgs_son), 2)
        del orgs_son[0]['id']
        del orgs_son[1]['id']
        expected = [
            {
                'name': 'Primary',
                'deleted': False,
                'locations': [{
                    'description': 'Nowhere',
                }],
                'meta': {
                    'assetTypes': ['water wholesale'],
                }
            }, {
                'name': 'Utility',
                'deleted': False,
                'locations': [{
                    'description': 'Somewhere',
                }],
                'meta': {
                    'assetTypes': ['water local'],
                }
            }
        ]
        self.assertEqual(orgs_son, expected)


class UserTest(base.AqHttpTestBase):

    def test_list_org(self):
        with base.mock_user('admin'):
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
                'deleted': False,
                'organisation': {
                    'name': 'Primary',
                    'deleted': False,
                }
            }, {
                'name': 'Author',
                'deleted': False,
                'organisation': {
                    'name': 'Primary',
                    'deleted': False,
                }
            }
        ]
        self.assertEqual(orgs_son, expected)


class OrgAuthzTest(base.AqHttpTestBase):

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
                'locations': [{
                    'description': 'Foo',
                    'region': 'Foo',
                }],
                'meta': {
                    'numberOfCustomers': 0,
                }
            }
            with base.mock_user(user):
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

            to_son = ToSon(
                r'/id$',
                r'/name$',
                r'/locations.*$',
                r'/meta.*$',
            )
            to_son.exclude(
                r'/locations/[0-9]+/id$',
                r'/locations/[0-9]+/organisation.*$',
                r'/meta/id$',
                r'/meta/organisation.*$',
            )
            org_son = to_son(org)

        with base.mock_user(user_email):

            post_data = org_son.copy()
            response = self.fetch(
                "/organisation/%s.json" % org_son['id'], method='PUT',
                body=json_encode(post_data))
        self.assertIn(reason, response.reason)
        self.assertEqual(code, response.code)


class UserAuthzTest(base.AqHttpTestBase):

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

        with base.mock_user(user_email), \
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

        with base.mock_user('admin'):
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

            to_son = ToSon(
                r'/id$',
                # Root-only: include everything
                r'^/[^/]+$',
                # Exclude password
                r'!/password$'
            )
            user_son = to_son(user)

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
            with base.mock_user(user_email):
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
            post_data['deleted'] = True
            with base.mock_user(user_email):
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

            to_son = ToSon(r'/id$', r'/name$')
            org_son = to_son(org)

            user = session.query(model.AppUser).\
                    filter(func.lower(model.AppUser.email) ==
                           func.lower(user_email)).one()

            user_son = to_son(user)
            user_son['organisation'] = org_son

            with base.mock_user(user_email):
                response = self.fetch(
                    "/user/%s.json" % user_son['id'], method='PUT',
                    body=json_encode(user_son))
                self.assertIn(reason, response.reason, msg=user_email)
                self.assertEqual(code, response.code)


class PasswordTest(base.AqHttpTestBase):

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
