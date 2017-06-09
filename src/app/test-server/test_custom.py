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


class CustomQueryTest(base.AqHttpTestBase):

    def test_create(self):
        son = {
            'title': 'Foo report',
            'description': "Foo bar baz",
            'text': "SELECT * FROM organisation",
        }
        with base.mock_user('admin'):
            response_son = self.fetch(
                "/custom_query.json", method='POST',
                body=json_encode(son), decode=True)

        for k in son:
            self.assertIn(k, response_son)
            self.assertEqual(son[k], response_son[k])

        qid = response_son['id']
        with base.mock_user('admin'):
            response_son = self.fetch(
                "/custom_query/%s.json" % qid, method='GET',
                decode=True)

        self.assertEqual(qid, response_son['id'])
        for k in son:
            self.assertIn(k, response_son)
            self.assertEqual(son[k], response_son[k])
