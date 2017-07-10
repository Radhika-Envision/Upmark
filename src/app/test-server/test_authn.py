
import urllib

from tornado.escape import json_decode, json_encode

import base
import model


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
            body=urllib.parse.urlencode(post_data), expected=302)
        self.assertIn('user="";', response.headers['set-cookie'])
        self.assertIn('superuser="";', response.headers['set-cookie'])

        post_data['password'] = 'foo'
        response = self.fetch(
            "/login", follow_redirects=False, method='POST',
            body=urllib.parse.urlencode(post_data), expected=302)
        self.assertIn('user=', response.headers['set-cookie'])

    def test_authenticated_root(self):
        with base.mock_user('admin'):
            response = self.fetch("/", expected=200)
        self.assertIn("Sign out", response.body.decode('utf8'))


class UserTest(base.AqHttpTestBase):

    def test_password_field(self):
        with model.session_scope() as session:
            org = (
                session.query(model.Organisation)
                .filter(model.Organisation.name == 'Primary')
                .first())
            user = model.AppUser(
                email='a', name='b', role='clerk', organisation=org)
            user.password = 'foo'
            session.add(user)
            session.flush()
            self.assertEqual(user.password, 'foo')
            self.assertNotEqual(str(user.password), 'foo')
            self.assertNotEqual(user.password, 'bar')


class PasswordTest(base.AqHttpTestBase):

    def test_password_strength(self):
        response = self.fetch(
            "/password.json", method='POST',
            body=json_encode({'password': 'foo'}),
            expected=403)

        with base.mock_user('clerk'):
            response = self.fetch(
                "/password.json", method='POST',
                body=json_encode({'password': 'foo'}),
                expected=200)
        son = json_decode(response.body)
        self.assertLess(son['strength'], 0.5)
        self.assertIn('charmix', son['improvements'])
        self.assertIn('length', son['improvements'])

        with base.mock_user('clerk'):
            response = self.fetch(
                "/password.json", method='POST',
                body=json_encode({'password': 'f0!'}),
                expected=200)
        son = json_decode(response.body)
        self.assertNotIn('charmix', son['improvements'])
        self.assertIn('length', son['improvements'])

        with base.mock_user('clerk'):
            response = self.fetch(
                "/password.json", method='POST',
                body=json_encode({'password': 'fooooooooooooooooooooooo'}),
                expected=200)
        son = json_decode(response.body)
        self.assertIn('charmix', son['improvements'])
        self.assertNotIn('length', son['improvements'])

        with base.mock_user('clerk'):
            response = self.fetch(
                "/password.json", method='POST',
                body=json_encode({'password': 'bdFiuo2807 g97834tq !'}),
                expected=200)
        son = json_decode(response.body)
        self.assertGreater(son['strength'], 0.9)
        self.assertNotIn('length', son['improvements'])
        self.assertNotIn('charmix', son['improvements'])
