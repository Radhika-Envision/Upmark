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
            survey = session.query(model.Survey).one()
            organisation = (session.query(model.Organisation)
                    .filter_by(name='Utility')
                    .one())
            hierarchy = (session.query(model.Hierarchy)
                    .filter_by(title='Hierarchy 1')
                    .one())

            survey_id = str(survey.id)
            organisation_id = str(organisation.id)
            hierarchy_id = str(hierarchy.id)

        with base.mock_user('admin'):
            ## purchase the survey
            self.fetch(
                "/organisation/%s/hierarchy/%s.json?surveyId=%s" %
                (organisation_id, hierarchy_id, survey_id),
                method='PUT', body='', expected=200)

        with base.mock_user('org_admin'):
            assessment_son = {'title': "Assessment"}
            assessment_son = self.fetch(
                "/assessment.json?orgId=%s&surveyId=%s&hierarchyId=%s" %
                (organisation_id, survey_id, hierarchy_id),
                method='POST', body=json_encode(assessment_son),
                expected=200, decode=False)

class ExporterAuthzTest(base.AqHttpTestBase):
    def setUp(self):
        super().setUp()
        with model.session_scope() as session:
            survey = session.query(model.Survey).one()
            organisation = (session.query(model.Organisation)
                    .filter_by(name='Utility')
                    .one())
            hierarchy = (session.query(model.Hierarchy)
                    .filter_by(title='Hierarchy 1')
                    .one())

            self.survey_id = str(survey.id)
            self.organisation_id = str(organisation.id)
            self.hierarchy_id = str(hierarchy.id)        

    def test_structure_exporter(self):
        with base.mock_user('author'):
            self.fetch("/export/survey/%s/hierarchy/%s.xlsx" % 
                (self.survey_id, self.hierarchy_id),
                method='GET', expected=200, encoding=None)

    def test_assessment_exporter(self):
        with base.mock_user('admin'):
            self.purchase_survey()
            self.add_assessment()

        with model.session_scope() as session:
            assessment = session.query(model.Assessment).filter(
                            model.Assessment.survey_id==self.survey_id,
                            model.Assessment.organisation_id==self.organisation_id,
                            model.Assessment.hierarchy_id==self.hierarchy_id).one()
            assessment_id = assessment.id

        with base.mock_user('author'):
            self.fetch(
                "/export/assessment/%s.xlsx" % assessment_id,
                method='GET', expected=403, decode=False, encoding=None)

        with base.mock_user('consultant'):
            self.fetch(
                "/export/assessment/%s.xlsx" % assessment_id,
                method='GET', expected=200, decode=False, encoding=None)

        with base.mock_user('clerk'):
            self.fetch(
                "/export/assessment/%s.xlsx" % assessment_id,
                method='GET', expected=200, decode=False, encoding=None)


    # def test_response_exporter(self):
    #     with base.mock_user('admin'):
    #         self.purchase_survey()
    #         self.add_assessment()

    #     with model.session_scope() as session:
    #         assessment = session.query(model.Assessment).filter(
    #                         model.Assessment.survey_id==self.survey_id,
    #                         model.Assessment.organisation_id==self.organisation_id,
    #                         model.Assessment.hierarchy_id==self.hierarchy_id).one()
    #         assessment_id = assessment.id
    #         log.info("assessment:%s", assessment)

    #     with base.mock_user('author'):
    #         self.fetch(
    #             "/export/response/%s.xlsx" % assessment_id,
    #             method='GET', expected=403, decode=False, encoding=None)

    #     with base.mock_user('consultant'):
    #         self.fetch(
    #             "/export/response/%s.xlsx" % assessment_id,
    #             method='GET', expected=403, decode=False, encoding=None)

    #     with base.mock_user('org_admin'):
    #         self.fetch(
    #             "/export/response/%s.xlsx" % assessment_id,
    #             method='GET', expected=200, decode=False, encoding=None)

    def purchase_survey(self):
        self.fetch(
            "/organisation/%s/hierarchy/%s.json?surveyId=%s" %
            (self.organisation_id, self.hierarchy_id, self.survey_id),
            method='PUT', body='', expected=200)

    def add_assessment(self):
        assessment_son = {'title': "Assessment"}
        assessment_son = self.fetch(
            "/assessment.json?orgId=%s&surveyId=%s&hierarchyId=%s" %
            (self.organisation_id, self.survey_id, self.hierarchy_id),
            method='POST', body=json_encode(assessment_son),
        expected=200, decode=False)