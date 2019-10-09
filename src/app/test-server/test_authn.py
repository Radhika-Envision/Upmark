
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
            'email': 'clerk',
            'password': 'bar'
        }
        response = self.fetch(
            "/login", follow_redirects=False, method='POST',
            body=urllib.parse.urlencode(post_data), expected=302)
        self.assertRegex(
            response.headers['set-cookie'], r'(^|\W)user=".+";')
        self.assertRegex(
            response.headers['set-cookie'], r'(^|\W)superuser="";')

        post_data = {
            'email': 'admin',
            'password': 'bar'
        }
        response = self.fetch(
            "/login", follow_redirects=False, method='POST',
            body=urllib.parse.urlencode(post_data), expected=302)
        # Confirm that cookie is cleared
        self.assertRegex(
            response.headers['set-cookie'], r'(^|\W)user="";')
        self.assertRegex(
            response.headers['set-cookie'], r'(^|\W)superuser="";')

        post_data['password'] = 'foo'
        response = self.fetch(
            "/login", follow_redirects=False, method='POST',
            body=urllib.parse.urlencode(post_data), expected=302)
        self.assertRegex(
            response.headers['set-cookie'], r'(^|\W)user=".+";')
        self.assertRegex(
            response.headers['set-cookie'], r'(^|\W)superuser=yes;')

    def test_logout(self):
        response = self.fetch(
            "/logout", follow_redirects=False, method='GET', expected=302)
        self.assertRegex(
            response.headers['set-cookie'], r'(^|\W)user="";')
        self.assertRegex(
            response.headers['set-cookie'], r'(^|\W)superuser="";')

    def test_authenticated_root(self):
        with base.mock_user('admin'):
            response = self.fetch("/", expected=200)
        self.assertIn("Sign out", response.body.decode('utf8'))

    def test_impersonate(self):
        users = [
            ('clerk', 'author', 403, "rank is too low"),
            ('org_admin', 'clerk', 403, "rank is too low"),
            ('author', 'clerk', 403, "rank is too low"),
            ('consultant', 'clerk', 403, "rank is too low"),
            ('authority', 'clerk', 403, "rank is too low"),
            ('author', 'clerk', 403, "rank is too low"),
            ('clerk', 'clerk_b', 403, "rank is too low"),
            ('super_admin', 'clerk', 200, 'OK'),
            ('super_admin', 'org_admin', 200, 'OK'),
            ('super_admin', 'author', 200, 'OK'),
            ('super_admin', 'consultant', 200, 'OK'),
            ('super_admin', 'authority', 200, 'OK'),
            ('super_admin', 'author', 200, 'OK'),
            ('super_admin', 'admin', 200, 'OK'),
            ('super_admin', 'clerk_b', 200, 'OK'),
            ('admin', 'clerk', 200, 'OK'),
            ('admin', 'org_admin', 200, 'OK'),
            ('admin', 'consultant', 200, 'OK'),
            ('admin', 'authority', 200, 'OK'),
            ('admin', 'author', 200, 'OK'),
            ('admin', 'admin', 200, 'OK'),
            ('admin', 'super_admin', 403, 'rank is too low'),
            ('admin', 'clerk_b', 403, 'not a memeber of that survey group'),
        ]

        for super_email, user_email, code, reason in users:
            with model.session_scope() as session:
                user = (
                    session.query(model.AppUser)
                    .filter(model.AppUser.email == user_email)
                    .first())
                user_id = user.id
            with base.mock_user(user_email, super_email):
                response = self.fetch(
                    "/impersonate/{}".format(user_id), method='PUT',
                    body='')
                self.assertIn(
                    reason, response.reason,
                    "{} failed to impersonate {}".format(
                        super_email, user_email))
                self.assertEqual(code, response.code)

    def test_impersonate_expired(self):
        '''
        Ensure superusers can't keep impersonating after jurisdiction
        changes.
        '''
        with model.session_scope() as session:
            admin = (
                session.query(model.AppUser)
                .filter(model.AppUser.email == 'admin')
                .first())
            clerk = (
                session.query(model.AppUser)
                .filter(model.AppUser.email == 'clerk')
                .first())

            with base.mock_user(user_email='clerk', super_email='admin'):
                # Wrong group; fails
                self.set_groups(clerk, 'banana')
                session.commit()
                response = self.fetch(
                    "/program.json".format(), method='GET',
                    follow_redirects=False, expected=403)
                self.assertIn(
                    "not a memeber of that survey group", response.reason)

                # Right group; works
                self.set_groups(clerk, 'apple')
                session.commit()
                response = self.fetch(
                    "/program.json".format(), method='GET',
                    follow_redirects=False, expected=200)
                self.assertIn(
                    "OK", response.reason)

                # Impersonated user disabled; fails
                clerk.deleted = True
                admin.deleted = False
                session.commit()
                response = self.fetch(
                    "/program.json".format(), method='GET',
                    follow_redirects=False, expected=403)
                self.assertIn(
                    "account has been disabled", response.reason)

                # Superuser (true user) disabled; fails
                clerk.deleted = False
                admin.deleted = True
                session.commit()
                response = self.fetch(
                    "/program.json".format(), method='GET',
                    follow_redirects=False, expected=403)
                self.assertIn(
                    "account has been disabled", response.reason)


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
