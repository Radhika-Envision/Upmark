import datetime
import logging
import os
import pprint
import unittest
from unittest import mock

from bunch import Bunch
import sqlalchemy
from sqlalchemy.sql import func
from sqlalchemy.orm.session import make_transient
from tornado.escape import json_encode
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

import app
import authz
import base
import model
from utils import ToSon


log = logging.getLogger('app.test.test_authz')


class AuthzMechanismTest(unittest.TestCase):
    def test_policy(self):
        policy = authz.Policy()

        policy.declare({
            'name': 'admin',
            'description': "the administrator role",
            'rule': 's.has_role("admin")',
        })
        policy.declare({
            'name': '_own_user',
            'description': "you are the owner",
            'rule': 'user.id == s.user.id',
        })
        policy.declare({
            'name': 'user_add',
            'description': "permission to add a new user",
            'rule': '@admin or (@org_admin and @_own_org)',
        })

        user_policy = policy.derive({
            's': Bunch(
                has_role=lambda name: True,
                user=Bunch(id='foo')
            ),
            'user': Bunch(id='foo')
        })
        self.assertEqual(user_policy.check('user_add'), True)

        user_policy = policy.derive({
            's': Bunch(
                has_role=lambda name: False,
                user=Bunch(id='foo')
            ),
            'user': Bunch(id='foo')
        })
        self.assertEqual(user_policy.check('user_add'), False)

        user_policy = policy.derive({
            's': Bunch(
                has_role=lambda name: True,
                user=Bunch(id='foo')
            ),
            'user': Bunch(id='bar')
        })
        self.assertEqual(user_policy.check('user_add'), False)

        with self.assertRaises(authz.AuthzError):
            user_policy.check('missing_rule')


class StatisticsAuthzTest(base.AqHttpTestBase):

    ### There is no meaning for testing authz for statistics.
    ### Because user only request for whole survey statistics.
    ### and for submission, user alredy checked submission authz
    ### therefore only testing for the survey is purchased or not for
    ### the organization is important.
    def test_get_statistics(self):
        with model.session_scope() as session:
            program = session.query(model.Program).one()
            organisation = (session.query(model.Organisation)
                    .filter_by(name='Utility')
                    .one())
            survey = (session.query(model.Survey)
                    .filter_by(title='Survey 1')
                    .one())

            self.program_id = str(program.id)
            self.organisation_id = str(organisation.id)
            self.survey_id = str(survey.id)

        with base.mock_user('consultant'):
            self.fetch(
                "/report/sub/stats/program/%s/survey/%s.json?approval=reviewed" % (
                    self.program_id, self.survey_id),
                method='GET', expected=200, decode=False)

        with base.mock_user('authority'):
            self.fetch(
                "/report/sub/stats/program/%s/survey/%s.json?approval=reviewed" % (
                    self.program_id, self.survey_id),
                method='GET', expected=200, decode=False)

        with base.mock_user('clerk'):
            self.fetch(
                "/report/sub/stats/program/%s/survey/%s.json?approval=reviewed" % (
                    self.program_id, self.survey_id),
                method='GET', expected=403, decode=False)

        # Before purchase survey
        with base.mock_user('clerk'):
            self.fetch(
                "/report/sub/stats/program/%s/survey/%s.json?approval=reviewed" % (
                    self.program_id, self.survey_id),
                method='GET', expected=403, decode=False)

        # After purchase survey
        with base.mock_user('admin'):
            self.purchase_program()

        with base.mock_user('clerk'):
            self.fetch(
                "/report/sub/stats/program/%s/survey/%s.json?approval=reviewed" % (
                    self.program_id, self.survey_id),
                method='GET', expected=200, decode=False)

    def purchase_program(self):
        self.fetch(
            "/organisation/%s/survey/%s.json?programId=%s" %
            (self.organisation_id, self.survey_id, self.program_id),
            method='PUT', body='', expected=200)



class ExporterAuthzTest(base.AqHttpTestBase):
    def setUp(self):
        super().setUp()
        with model.session_scope() as session:
            program = session.query(model.Program).one()
            organisation = (session.query(model.Organisation)
                    .filter_by(name='Utility')
                    .one())
            survey = (session.query(model.Survey)
                    .filter_by(title='Survey 1')
                    .one())

            self.program_id = str(program.id)
            self.organisation_id = str(organisation.id)
            self.survey_id = str(survey.id)
            log.info("program_id: %s", self.program_id)
            log.info("organisation_id: %s", self.organisation_id)
            log.info("survey_id: %s", self.survey_id)

    def test_structure_exporter_with_purchase(self):
        with base.mock_user('admin'):
            self.fetch("/report/prog/export/%s/survey/%s/nested.xlsx" %
                (self.program_id, self.survey_id),
                method='GET', expected=200)
            self.fetch("/report/prog/export/%s/survey/%s/tabular.xlsx" %
                (self.program_id, self.survey_id),
                method='GET', expected=200)

    def test_submission_exporter(self):
        with base.mock_user('admin'):
            self.purchase_program()
            self.add_submission()

        with model.session_scope() as session:
            submission = session.query(model.Submission).filter(
                            model.Submission.program_id==self.program_id,
                            model.Submission.organisation_id==self.organisation_id,
                            model.Submission.survey_id==self.survey_id).first()
            submission_id = submission.id

        with base.mock_user('author'):
            self.fetch(
                "/report/sub/export/%s/tabular.xlsx" % submission_id,
                method='GET', expected=403, decode=False)
            self.fetch(
                "/report/sub/export/%s/nested.xlsx" % submission_id,
                method='GET', expected=403, decode=False)

        with base.mock_user('consultant'):
            self.fetch(
                "/report/sub/export/%s/tabular.xlsx" % submission_id,
                method='GET', expected=200, decode=False)
            self.fetch(
                "/report/sub/export/%s/nested.xlsx" % submission_id,
                method='GET', expected=200, decode=False)

        with base.mock_user('clerk'):
            self.fetch(
                "/report/sub/export/%s/tabular.xlsx" % submission_id,
                method='GET', expected=200, decode=False)
            self.fetch(
                "/report/sub/export/%s/nested.xlsx" % submission_id,
                method='GET', expected=200, decode=False)

    def purchase_program(self):
        self.fetch(
            "/organisation/%s/survey/%s.json?programId=%s" %
            (self.organisation_id, self.survey_id, self.program_id),
            method='PUT', body='', expected=200)

    def add_submission(self):
        submission_son = {
            'title': "Submission",
            'created': datetime.datetime(2012, 1, 1).timestamp(),
        }
        submission_son = self.fetch(
            "/submission.json?organisationId=%s&programId=%s&surveyId=%s" %
            (self.organisation_id, self.program_id, self.survey_id),
            method='POST', body=json_encode(submission_son),
        expected=200, decode=False)
