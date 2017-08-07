from tornado.escape import json_encode

import base


class CustomQueryTest(base.AqHttpTestBase):

    def test_create(self):
        son = {
            'title': 'Foo report',
            'description': "Foo bar baz",
            'text': "SELECT * FROM organisation",
        }
        with base.mock_user('super_admin'):
            response_son = self.fetch(
                "/custom_query.json", method='POST',
                body=json_encode(son), expected=200, decode=True)

        for k in son:
            self.assertIn(k, response_son)
            self.assertEqual(son[k], response_son[k])

        qid = response_son['id']
        with base.mock_user('super_admin'):
            response_son = self.fetch(
                "/custom_query/%s.json" % qid, method='GET',
                decode=True)

        self.assertEqual(qid, response_son['id'])
        for k in son:
            self.assertIn(k, response_son)
            self.assertEqual(son[k], response_son[k])
