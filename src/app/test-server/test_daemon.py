import logging
import unittest
from unittest import mock

import sqlalchemy as sa
from sqlalchemy.sql import func
from sqlalchemy.orm.session import make_transient
from tornado.escape import json_encode
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

import base
import model
import notifications
import recalculate
import utils


log = logging.getLogger('app.test_daemon')


class DaemonTest(base.AqHttpTestBase):
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

        config = utils.get_config("notification.yaml")
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

    def create_assessment(self):
        # Respond to a survey
        with model.session_scope() as session:
            survey = session.query(model.Survey).one()
            user = (session.query(model.AppUser)
                    .filter_by(email='clerk')
                    .one())
            organisation = (session.query(model.Organisation)
                    .filter_by(name='Utility')
                    .one())
            hierarchy = (session.query(model.Hierarchy)
                    .filter_by(title='Hierarchy 1')
                    .one())
            assessment = model.Assessment(
                survey_id=survey.id,
                organisation_id=organisation.id,
                hierarchy_id=hierarchy.id,
                title="Submission",
                approval='draft')
            session.add(assessment)

            for m in survey.measures:
                if not any(p.hierarchy_id == hierarchy.id for p in m.parents):
                    continue
                response = model.Response(
                    survey_id=survey.id,
                    measure_id=m.id,
                    assessment=assessment,
                    user_id=user.id)
                response.attachments = []
                response.not_relevant = False
                response.modified = sa.func.now()
                response.approval = 'final'
                response.comment = "Response for %s" % m.title
                session.add(response)
                response.response_parts = [{'index': 1, 'note': "Yes"}]

            assessment.update_stats_descendants()
            functions = list(assessment.rnodes)
            self.assertAlmostEqual(functions[0].score, 600)
            self.assertAlmostEqual(functions[1].score, 0)
            self.assertAlmostEqual(functions[0].qnode.total_weight, 600)
            self.assertAlmostEqual(functions[1].qnode.total_weight, 0)

            return assessment.id

    def test_recalculate(self):
        aid = self.create_assessment()
        with model.session_scope() as session:
            assessment = session.query(model.Assessment).get(aid)
            sid = assessment.survey_id
            process_id = assessment.hierarchy.qnodes[0].children[0].id
            function_2_id = assessment.hierarchy.qnodes[1].id

        # Move a process (qnode) to a different function
        with base.mock_user('author'):
            url = "/qnode/{}.json?surveyId={}".format(process_id, sid)
            qnode_son = self.fetch(
                url, method='GET', expected=200, decode=True)
            qnode_son = self.fetch(
                url + "&parentId={}".format(function_2_id),
                method='PUT', expected=200, decode=True,
                body=json_encode(qnode_son))

        # Check that rnode score is out of date
        with model.session_scope() as session:
            assessment = session.query(model.Assessment).get(aid)
            functions = list(assessment.rnodes)
            self.assertAlmostEqual(functions[0].score, 600)
            self.assertAlmostEqual(functions[1].score, 0)
            self.assertAlmostEqual(functions[0].qnode.total_weight, 300)
            self.assertAlmostEqual(functions[1].qnode.total_weight, 300)

        # Run recalculation script
        config = utils.get_config("recalculate.yaml")
        messages = None
        def send(config, msg):
            messages.append(msg)

        messages = []
        with mock.patch('recalculate.send', send):
            recalculate.process_once(config)
            self.assertEqual(len(messages), 0)

        # Check that rnode score is no longer out of date
        with model.session_scope() as session:
            assessment = session.query(model.Assessment).get(aid)
            functions = list(assessment.rnodes)
            self.assertAlmostEqual(functions[0].score, 300)
            self.assertAlmostEqual(functions[1].score, 300)
            self.assertAlmostEqual(functions[0].qnode.total_weight, 300)
            self.assertAlmostEqual(functions[1].qnode.total_weight, 300)

    def test_recalculate_failure(self):
        aid = self.create_assessment()
        with model.session_scope() as session:
            assessment = session.query(model.Assessment).get(aid)
            sid = assessment.survey_id
            process_id = assessment.hierarchy.qnodes[0].children[0].id
            function_2_id = assessment.hierarchy.qnodes[1].id

        # Move a process (qnode) to a different function
        with base.mock_user('author'):
            url = "/qnode/{}.json?surveyId={}".format(process_id, sid)
            qnode_son = self.fetch(
                url, method='GET', expected=200, decode=True)
            qnode_son = self.fetch(
                url + "&parentId={}".format(function_2_id),
                method='PUT', expected=200, decode=True,
                body=json_encode(qnode_son))

        # Run recalculation script
        config = utils.get_config("recalculate.yaml")
        messages = None
        def send(config, msg):
            messages.append(msg)

        def update_stats_descendants(self):
            raise model.ModelError("Test failure")

        messages = []
        with mock.patch('recalculate.send', send), \
                mock.patch('model.Assessment.update_stats_descendants',
                           update_stats_descendants):
            recalculate.process_once(config)
            self.assertEqual(len(messages), 1)
