import datetime
import logging
import time
import unittest
from unittest import mock

import sqlalchemy as sa
from sqlalchemy.sql import func
from sqlalchemy.orm.session import make_transient
from tornado.escape import json_encode
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

import base
import config as app_config
import model
import notifications
import recalculate
from response_type import ResponseTypeError
from score import Calculator
import utils


log = logging.getLogger('app.test.test_daemon')


class ExpectedError(Exception):
    pass

class UnexpectedError(Exception):
    pass


class DaemonTest(base.AqHttpTestBase):
    def test_timeline(self):
        # Delete a qnode; this should subscribe to the program and add an event
        # to the timeline
        with base.mock_user('author'):
            program_sons = self.fetch(
                "/program.json", method='GET',
                expected=200, decode=True)
            sid = program_sons[0]['id']

            survey_sons = self.fetch(
                "/survey.json?programId=%s&term=Survey%%201" % sid,
                method='GET', expected=200, decode=True)
            hid = survey_sons[0]['id']

            url = "/qnode.json?programId=%s&surveyId=%s&root=&deleted=false" % (sid, hid)
            qnode_sons = self.fetch(
                url, method='GET', expected=200, decode=True)
            self.assertTrue(all(q['deleted'] == False for q in qnode_sons))
            qid1 = qnode_sons[0]['id']
            qid2 = qnode_sons[1]['id']

            a_son = self.fetch(
                "/activity.json?period=604800",
                method='GET', expected=200, decode=True)
            self.assertEqual(len(a_son['actions']), 0)

            sub_son = self.fetch(
                "/subscription/qnode/{},{}.json".format(qid1, sid),
                method='GET', expected=200, decode=True)
            ss = [sub['subscribed'] for sub in sub_son]
            self.assertTrue(all(s is None for s in ss))

            q_son = self.fetch(
                "/qnode/{}.json?programId={}".format(qid1, sid),
                method='DELETE', expected=200)

            sub_son = self.fetch(
                "/subscription/qnode/{},{}.json".format(qid1, sid),
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
        def send(config, msg, to):
            messages[to] = msg

        messages = {}
        with mock.patch('notifications.send', send):
            n_sent = notifications.process_once(config)
            self.assertEqual(n_sent, 6)
            self.assertEqual(len(messages), 6)

        with model.session_scope() as session:
            app_base_url = app_config.get_setting(session, 'app_base_url')

        author_checked = False
        for to, m in messages.items():
            self.assertIn("\nAdmin said:\nFoo\n", str(m))

            # Assumes base URL is used in the notification email, this could
            # be optional
            self.assertIn(app_base_url, str(m))

            if to == 'author':
                self.assertIn(
                    '\nFunction 1\nAuthor deleted this survey category\n',
                    str(m))
                log.info("Notification email: %s", str(m))
                author_checked = True
        self.assertTrue(author_checked)

        time.sleep(0.1)

        # Delete another qnode
        with base.mock_user('author'):
            q_son = self.fetch(
                "/qnode/{}.json?programId={}".format(qid2, sid),
                method='DELETE', expected=200)

        # Run again, and make sure no nofications send (because not enough time
        # has elapsed since the last email)
        messages = {}
        with mock.patch('notifications.send', send):
            n_sent = notifications.process_once(config)
            self.assertEqual(n_sent, 0)
            self.assertEqual(len(messages), 0)

        time.sleep(0.1)

        sa_func_now = sa.func.now
        def next_week():
            return sa_func_now() + datetime.timedelta(days=7)

        # Run again, pretending to be in the future, and check that another
        # notification is sent
        messages = {}
        with mock.patch('notifications.send', send), \
                mock.patch('notifications.func.now', next_week):
            n_sent = notifications.process_once(config)
            self.assertEqual(n_sent, 1)
            self.assertEqual(len(messages), 1)

        author_checked = False
        for to, m in messages.items():
            if to == 'author':
                self.assertIn(
                    '\nFunction 2\nAuthor deleted this survey category\n',
                    str(m))
                log.info("Notification email: %s", str(m))
                author_checked = True
        self.assertTrue(author_checked)

    def test_timeline_failure(self):
        messages = None
        def send(config, msg, to):
            messages.append(msg)

        messages = []
        with mock.patch('notifications.send', send), \
                mock.patch('notifications.process_once',
                           side_effect=ExpectedError), \
                self.assertRaises(ExpectedError), \
                mock.patch('notifications.time.sleep',
                           side_effect=UnexpectedError):
            notifications.process_loop()
        self.assertEqual(len(messages), 1)

    def create_submission(self):
        # Respond to a survey
        with model.session_scope() as session:
            program = session.query(model.Program).one()
            user = (session.query(model.AppUser)
                    .filter_by(email='clerk')
                    .one())
            organisation = (session.query(model.Organisation)
                    .filter_by(name='Utility')
                    .one())
            survey = (session.query(model.Survey)
                    .filter_by(title='Survey 1')
                    .one())
            submission = model.Submission(
                program_id=program.id,
                organisation_id=organisation.id,
                survey_id=survey.id,
                title="Submission",
                approval='draft')
            session.add(submission)

            for m in program.measures:
                # Preload response type to avoid autoflush
                response_type = m.response_type
                qnode_measure = m.get_qnode_measure(survey)
                if not qnode_measure:
                    continue
                response = model.Response(
                    submission=submission,
                    qnode_measure=qnode_measure,
                    user=user)
                response.attachments = []
                response.not_relevant = False
                response.modified = sa.func.now()
                response.approval = 'final'
                response.comment = "Response for %s" % m.title
                session.add(response)
                if response_type.name == 'Yes / No':
                    response.response_parts = [{'index': 1, 'note': "Yes"}]
                else:
                    response.response_parts = [{'value': 1}]

            calculator = Calculator.scoring(submission)
            calculator.mark_entire_survey_dirty(submission.survey)
            calculator.execute()

            functions = list(submission.rnodes)
            self.assertAlmostEqual(functions[0].score, 33)
            self.assertAlmostEqual(functions[1].score, 0)
            self.assertAlmostEqual(functions[0].qnode.total_weight, 33)
            self.assertAlmostEqual(functions[1].qnode.total_weight, 0)

            return submission.id

    def test_recalculate(self):
        aid = self.create_submission()
        with model.session_scope() as session:
            submission = session.query(model.Submission).get(aid)
            sid = submission.program_id
            process_id = submission.survey.qnodes[0].children[0].id
            function_2_id = submission.survey.qnodes[1].id

        # Move a process (qnode) to a different function
        with base.mock_user('author'):
            url = "/qnode/{}.json?programId={}".format(process_id, sid)
            qnode_son = self.fetch(
                url, method='GET', expected=200, decode=True)
            qnode_son = self.fetch(
                url + "&parentId={}".format(function_2_id),
                method='PUT', expected=200, decode=True,
                body=json_encode(qnode_son))

        # Check that rnode score is out of date
        with model.session_scope() as session:
            submission = session.query(model.Submission).get(aid)
            functions = list(submission.rnodes)
            self.assertAlmostEqual(functions[0].score, 3 + 6 + 11 + 13)
            self.assertAlmostEqual(functions[1].score, 0)
            self.assertAlmostEqual(functions[0].qnode.total_weight, 11 + 13)
            self.assertAlmostEqual(functions[1].qnode.total_weight, 3 + 6)

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
            submission = session.query(model.Submission).get(aid)
            functions = list(submission.rnodes)
            self.assertAlmostEqual(functions[0].score, 11 + 13)
            self.assertAlmostEqual(functions[1].score, 3 + 6)
            self.assertAlmostEqual(functions[0].qnode.total_weight, 11 + 13)
            self.assertAlmostEqual(functions[1].qnode.total_weight, 3 + 6)

    def test_recalculate_failure(self):
        aid = self.create_submission()
        with model.session_scope() as session:
            submission = session.query(model.Submission).get(aid)
            sid = submission.program_id
            process_id = submission.survey.qnodes[0].children[0].id
            function_2_id = submission.survey.qnodes[1].id

        # Move a process (qnode) to a different function
        with base.mock_user('author'):
            url = "/qnode/{}.json?programId={}".format(process_id, sid)
            qnode_son = self.fetch(
                url, method='GET', expected=200, decode=True)
            qnode_son = self.fetch(
                url + "&parentId={}".format(function_2_id),
                method='PUT', expected=200, decode=True,
                body=json_encode(qnode_son))

        # Run recalculation script
        config = utils.get_config("recalculate.yaml")
        messages = None
        def send(config, msg, to):
            messages.append(msg)

        messages = []
        with mock.patch('recalculate.send', send), \
                mock.patch('response_type.ResponseType.validate',
                           side_effect=ResponseTypeError):
            count, n_errors = recalculate.process_once(config)
            self.assertEqual(n_errors, 1)

        messages = []
        with mock.patch('recalculate.send', send), \
                mock.patch('recalculate.process_once',
                           side_effect=ExpectedError), \
                self.assertRaises(ExpectedError), \
                mock.patch('recalculate.time.sleep',
                           side_effect=UnexpectedError):
            recalculate.process_loop()
        self.assertEqual(len(messages), 1)
