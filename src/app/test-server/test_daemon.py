import logging
import unittest
from unittest import mock

import sqlalchemy
from sqlalchemy.sql import func
from sqlalchemy.orm.session import make_transient
from tornado.escape import json_encode
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

import base
import model
import notifications


log = logging.getLogger('app.test_daemon')


class NotificationTest(base.AqHttpTestBase):
    def test_timeline(self):
        # Delete a qnode; this should subscribe to the survey and add an event
        # to the timeline
        with base.mock_user('author'):
            survey_sons = self.fetch(
                "/survey.json", method='GET',
                expected=200, decode=True)
            sid = survey_sons[0]['id']

            hierarchy_sons = self.fetch(
                "/hierarchy.json?surveyId=%s" % sid,
                method='GET', expected=200, decode=True)
            hid = hierarchy_sons[0]['id']

            url = "/qnode.json?surveyId=%s&hierarchyId=%s&root=" % (sid, hid)
            qnode_sons = self.fetch(
                url, method='GET', expected=200, decode=True)
            qid = qnode_sons[0]['id']

            a_son = self.fetch(
                "/activity.json?period=604800",
                method='GET', expected=200, decode=True)
            self.assertEqual(len(a_son['actions']), 0)

            sub_son = self.fetch(
                "/subscription/qnode/{},{}.json".format(qid, sid),
                method='GET', expected=200, decode=True)
            ss = [sub['subscribed'] for sub in sub_son]
            self.assertTrue(all(s is None for s in ss))

            q_son = self.fetch(
                "/qnode/{}.json?surveyId={}".format(qid, sid),
                method='DELETE', expected=200)

            sub_son = self.fetch(
                "/subscription/qnode/{},{}.json".format(qid, sid),
                method='GET', expected=200, decode=True)
            ss = [sub['subscribed'] for sub in sub_son]
            self.assertTrue(any(s is not None for s in ss))
            self.assertTrue(any(s is None for s in ss))

            a_son = self.fetch(
                "/activity.json?period=604800",
                method='GET', expected=200, decode=True)
            self.assertEqual(len(a_son['actions']), 1)

        with base.mock_user('admin'):
            self.fetch(
                "/activity.json",
                method='POST', expected=200, decode=True,
                body=json_encode({
                    'to': 'all',
                    'sticky': True,
                    'message': "Foo"
                }))

        config = notifications.get_config("notification.yaml.SAMPLE")
        messages = None
        def send(config, msg):
            messages.append(msg)

        messages = []
        with mock.patch('notifications.send', send):
            n_sent = notifications.process_once(config)
            self.assertEqual(n_sent, 6)
            self.assertEqual(len(messages), 6)

        for m in messages:
            self.assertIn("\nTo: %s\n" % m['to'], str(m))
            self.assertIn("\nAdmin said:\nFoo", str(m))
            if m['to'] == 'author':
                self.assertIn('\nAuthor deleted this survey category\n', str(m))
                log.info("Notification email: %s", str(m))

        messages = []
        with mock.patch('notifications.send', send):
            n_sent = notifications.process_once(config)
            self.assertEqual(n_sent, 0)
            self.assertEqual(len(messages), 0)
