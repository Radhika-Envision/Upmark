import logging
import os
import pprint
import unittest
from unittest import mock
import urllib

import sqlalchemy
from sqlalchemy.sql import func
from sqlalchemy.orm.session import make_transient
from tornado.escape import json_encode
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

import app
import base
import model
from utils import ToSon


log = logging.getLogger('app.test_authz')


class StatisticsAuthzTest(base.AqHttpTestBase):

    ### There is no meaning for testing authz for statistics.
    ### Because user only request for whole survey statistics.
    ### and for assessment, user alredy checked assessment authz
    ### therefore only testing for the survey is purchased or not for
    ### the organization is important.
    def test_get_statistics(self):
        with model.session_scope() as session:
            program = session.query(model.Program).one()
            organisation = (session.query(model.Organisation)
                    .filter_by(name='Utility')
                    .one())
            hierarchy = (session.query(model.Hierarchy)
                    .filter_by(title='Hierarchy 1')
                    .one())

            self.program_id = str(program.id)
            self.organisation_id = str(organisation.id)
            self.hierarchy_id = str(hierarchy.id)

        with base.mock_user('consultant'):
            self.fetch(
                "/statistics/%s.json" % self.program_id,
                method='GET', expected=200, decode=False)

        with base.mock_user('authority'):
            self.fetch(
                "/statistics/%s.json" % self.program_id,
                method='GET', expected=200, decode=False)

        with base.mock_user('clerk'):
            self.fetch(
                "/statistics/%s.json" % self.program_id,
                method='GET', expected=403, decode=False)

        # Before purchase survey
        with base.mock_user('clerk'):
            self.fetch(
                "/statistics/%s.json" % self.program_id,
                method='GET', expected=403, decode=False)

        # After purchase survey
        with base.mock_user('admin'):
            self.purchase_program()

        with base.mock_user('clerk'):
            self.fetch(
                "/statistics/%s.json" % self.program_id,
                method='GET', expected=200, decode=False)

    def purchase_program(self):
        self.fetch(
            "/organisation/%s/hierarchy/%s.json?programId=%s" %
            (self.organisation_id, self.hierarchy_id, self.program_id),
            method='PUT', body='', expected=200)



class ExporterAuthzTest(base.AqHttpTestBase):
    def setUp(self):
        super().setUp()
        with model.session_scope() as session:
            program = session.query(model.Program).one()
            organisation = (session.query(model.Organisation)
                    .filter_by(name='Utility')
                    .one())
            hierarchy = (session.query(model.Hierarchy)
                    .filter_by(title='Hierarchy 1')
                    .one())

            self.program_id = str(program.id)
            self.organisation_id = str(organisation.id)
            self.hierarchy_id = str(hierarchy.id)
            log.info("program_id: %s", self.program_id)
            log.info("organisation_id: %s", self.organisation_id)
            log.info("hierarchy_id: %s", self.hierarchy_id)

    def test_structure_exporter_with_purchase(self):
        with base.mock_user('admin'):
            self.fetch("/export/program/%s/hierarchy/%s/nested.xlsx" %
                (self.program_id, self.hierarchy_id),
                method='GET', expected=200, encoding=None)
            self.fetch("/export/program/%s/hierarchy/%s/tabular.xlsx" %
                (self.program_id, self.hierarchy_id),
                method='GET', expected=200, encoding=None)

    def test_assessment_exporter(self):
        with base.mock_user('admin'):
            self.purchase_program()
            self.add_assessment()

        with model.session_scope() as session:
            assessment = session.query(model.Assessment).filter(
                            model.Assessment.program_id==self.program_id,
                            model.Assessment.organisation_id==self.organisation_id,
                            model.Assessment.hierarchy_id==self.hierarchy_id).first()
            assessment_id = assessment.id

        with base.mock_user('author'):
            self.fetch(
                "/export/assessment/%s/tabular.xlsx" % assessment_id,
                method='GET', expected=403, decode=False, encoding=None)
            self.fetch(
                "/export/assessment/%s/nested.xlsx" % assessment_id,
                method='GET', expected=403, decode=False, encoding=None)

        with base.mock_user('consultant'):
            self.fetch(
                "/export/assessment/%s/tabular.xlsx" % assessment_id,
                method='GET', expected=200, decode=False, encoding=None)
            self.fetch(
                "/export/assessment/%s/nested.xlsx" % assessment_id,
                method='GET', expected=200, decode=False, encoding=None)

        with base.mock_user('clerk'):
            self.fetch(
                "/export/assessment/%s/tabular.xlsx" % assessment_id,
                method='GET', expected=200, decode=False, encoding=None)
            self.fetch(
                "/export/assessment/%s/nested.xlsx" % assessment_id,
                method='GET', expected=200, decode=False, encoding=None)

    def purchase_program(self):
        self.fetch(
            "/organisation/%s/hierarchy/%s.json?programId=%s" %
            (self.organisation_id, self.hierarchy_id, self.program_id),
            method='PUT', body='', expected=200)

    def add_assessment(self):
        assessment_son = {'title': "Assessment"}
        assessment_son = self.fetch(
            "/assessment.json?orgId=%s&programId=%s&hierarchyId=%s" %
            (self.organisation_id, self.program_id, self.hierarchy_id),
            method='POST', body=json_encode(assessment_son),
        expected=200, decode=False)
