import datetime
import json
import logging
import os
import pprint
import unittest
from unittest import mock

from sqlalchemy.sql import func
from sqlalchemy.orm.session import make_transient
from tornado.escape import json_encode
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

import app
import base
import model
from response_type import ExpressionError, ResponseTypeCache, ResponseError
from utils import ToSon


log = logging.getLogger('app.test_response')


TEST_RESPONSE_TYPES = [
    {
        "id": "yes-no",
        "name": "Yes / No",
        "parts": [
            {
                "id": "a",
                "type": "multiple_choice",
                "options": [
                    {"score": 0.0, "name": "No"},
                    {"score": 1.0, "name": "Yes"}
                ]
            }
        ]
    },
    {
        "id": "multi-part",
        "name": "Multi-part Multiple Choice",
        "parts": [
            {
                "id": "a",
                "type": "multiple_choice",
                "options": [
                    {"score": 0.0, "name": "No"},
                    {"score": 0.5, "name": "Maybe"},
                    {"score": 1.0, "name": "Yes"}
                ]
            },
            {
                "id": "b",
                "type": "multiple_choice",
                "options": [
                    {"score": 0.0, "name": "No"},
                    {"score": 0.5, "name": "Maybe", "if": "a >= 0.5"},
                    {"score": 1.0, "name": "Yes", "if": "a__i >= 2"}
                ]
            }
        ],
        "formula": "(a + b) * 0.5"
    },
    {
        "id": "numerical",
        "name": "Numerical",
        "parts": [
            {
                "id": "a",
                "type": "numerical",
                "lower": "0",
                "upper": "1",
            }
        ]
    },
    {
        "id": "numerical-multi",
        "name": "Multi-part Numerical",
        "parts": [
            {
                "id": "a",
                "type": "numerical",
                "lower": "0",
                "upper": "1",
            },
            {
                "id": "b",
                "type": "numerical",
                "lower": "a",
                "upper": "1",
            },
            {
                "id": "c",
                "type": "numerical",
                "lower": "a",
                "upper": "b",
            }
        ]
    },
    {
        "id": "comment",
        "name": "Comment Only (no score)",
        "parts": []
    }
]


class ResponseTypeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rts = ResponseTypeCache(TEST_RESPONSE_TYPES)

    def test_deserialise(self):
        proj_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..')

        with open(os.path.join(
                proj_dir, 'client', 'default_response_types.json')) as file:
            ResponseTypeCache(json.load(file))

        with open(os.path.join(
                proj_dir, 'server', 'aquamark_response_types.json')) as file:
            ResponseTypeCache(json.load(file))

    def test_comment_only(self):
        rt = self.rts['comment']
        self.assertEqual(rt.calculate_score([]), 0.0)

    def test_yesno(self):
        rt = self.rts['yes-no']
        self.assertEqual(rt.calculate_score([
            {'index': 0}
        ]), 0.0)

        self.assertEqual(rt.calculate_score([
            {'index': 1}
        ]), 1.0)

    def test_numerical(self):
        rt = self.rts['numerical']
        self.assertEqual(rt.calculate_score([
            {'value': 0.3}
        ]), 0.3)

    def test_multipart(self):
        rt = self.rts['multi-part']
        self.assertAlmostEqual(rt.calculate_score([
            {'index': 2},
            {'index': 1},
        ]), (1 + 0.5) * 0.5)

    def test_missing_part(self):
        with self.assertRaises(ResponseError):
            self.rts['yes-no'].calculate_score([])

        with self.assertRaises(ResponseError):
            self.rts['multi-part'].calculate_score([
                {'index': 0},
            ])

    def test_multiple_choise_out_of_range(self):
        with self.assertRaises(ResponseError):
            self.rts['yes-no'].calculate_score([
                {'index': 2},
            ])
        with self.assertRaises(ResponseError):
            self.rts['yes-no'].calculate_score([
                {'index': -1},
            ])

    def test_multiple_choice_predicate_violation(self):
        with self.assertRaises(ResponseError):
            self.rts['multi-part'].calculate_score([
                {'index': 1},
                {'index': 2},
            ])

    def test_numerical_predicate_violation(self):
        with self.assertRaises(ResponseError):
            self.rts['numerical'].calculate_score([
                {'value': -1},
            ])
        with self.assertRaises(ResponseError):
            self.rts['numerical'].calculate_score([
                {'value': 2},
            ])

        # The first two parts set the bounds for the third
        self.rts['numerical-multi'].calculate_score([
            {'value': 0.4},
            {'value': 0.6},
            {'value': 0.5},
        ])
        with self.assertRaises(ResponseError):
            self.rts['numerical-multi'].calculate_score([
                {'value': 0.4},
                {'value': 0.6},
                {'value': 0.3},
            ])
        with self.assertRaises(ResponseError):
            self.rts['numerical-multi'].calculate_score([
                {'value': 0.4},
                {'value': 0.6},
                {'value': 0.7},
            ])


class SubmissionTest(base.AqHttpTestBase):
    def test_create(self):
        with model.session_scope() as session:
            program = session.query(model.Program).one()
            organisation = (session.query(model.Organisation)
                    .filter_by(name='Utility')
                    .one())
            survey_1 = (session.query(model.Survey)
                    .filter_by(title='Survey 1')
                    .one())
            survey_2 = (session.query(model.Survey)
                    .filter_by(title='Survey 2')
                    .one())

            program_id = str(program.id)
            organisation_id = str(organisation.id)
            survey_1_id = str(survey_1.id)
            survey_2_id = str(survey_2.id)

        with base.mock_user('org_admin'):
            submission_son = {'title': "Submission"}
            submission_son = self.fetch(
                "/submission.json?orgId=%s&programId=%s&surveyId=%s" %
                (organisation_id, program_id, survey_1_id),
                method='POST', body=json_encode(submission_son),
                expected=403, decode=False)

        with base.mock_user('admin'):
            self.fetch(
                "/organisation/%s/survey/%s.json?programId=%s" %
                (organisation_id, survey_1_id, program_id),
                method='PUT', body='', expected=200)

        with base.mock_user('org_admin'):
            submission_son = {'title': "Submission"}
            submission_son = self.fetch(
                "/submission.json?orgId=%s&programId=%s&surveyId=%s" %
                (organisation_id, program_id, survey_1_id),
                method='POST', body=json_encode(submission_son),
                expected=200, decode=True)

    def test_duplicate(self):
        # Respond to a survey
        with model.session_scope() as session:
            program = session.query(model.Program).one()
            user = (session.query(model.AppUser)
                    .filter_by(email='clerk')
                    .one())
            organisation = (session.query(model.Organisation)
                    .filter_by(name='Utility')
                    .one())
            survey_1 = (session.query(model.Survey)
                    .filter_by(title='Survey 1')
                    .one())
            survey_2 = (session.query(model.Survey)
                    .filter_by(title='Survey 2')
                    .one())
            submission = model.Submission(
                program_id=program.id,
                organisation_id=organisation.id,
                survey_id=survey_1.id,
                title="First submission",
                approval='draft')
            session.add(submission)
            session.flush()

            for m in program.measures:
                if not any(p.survey_id == survey_1.id for p in m.parents):
                    continue
                response = model.Response(
                    program_id=program.id,
                    measure_id=m.id,
                    submission_id=submission.id,
                    user_id=user.id)
                response.attachments = []
                response.not_relevant = False
                response.modified = datetime.datetime.utcnow()
                response.approval = 'final'
                response.comment = "Response for %s" % m.title
                session.add(response)
                if m.response_type == 'yes-no':
                    response.response_parts = [{'index': 1, 'note': "Yes"}]
                else:
                    response.response_parts = [{'value': 1}]

                response.attachments.append(model.Attachment(
                    file_name="File %s 1" % m.title,
                    url="Bar",
                    storage='external',
                    organisation_id=organisation.id))
                response.attachments.append(model.Attachment(
                    file_name="File %s 2" % m.title,
                    url="Baz",
                    storage='external',
                    organisation_id=organisation.id))
                response.attachments.append(model.Attachment(
                    file_name="File %s 3" % m.title,
                    blob=b'A blob',
                    storage='external',
                    organisation_id=organisation.id))

            session.flush()

            submission.update_stats_descendants()
            submission.approval = 'final'
            session.flush()

            organisation_id = str(organisation.id)
            first_submission_id = str(submission.id)
            survey_1_id = str(survey_1.id)
            survey_2_id = str(survey_2.id)

        # Duplicate program
        with base.mock_user('author'):
            program_sons = self.fetch(
                "/program.json", method='GET',
                expected=200, decode=True)
            self.assertEqual(len(program_sons), 1)
            original_program_id = program_sons[0]['id']

            program_son = self.fetch(
                "/program/%s.json" % original_program_id, method='GET',
                expected=200, decode=True)

            program_son['title'] = "Duplicate program"

            program_son = self.fetch(
                "/program.json?duplicateId=%s" % original_program_id,
                method='POST', body=json_encode(program_son),
                expected=200, decode=True)
            new_program_id = program_son['id']

        # Open (purchase) both new surveys for organisation
        with base.mock_user('admin'):
            self.fetch(
                "/organisation/%s/survey/%s.json?programId=%s" %
                (organisation_id, survey_1_id, new_program_id),
                method='PUT', body='', expected=200)
            self.fetch(
                "/organisation/%s/survey/%s.json?programId=%s" %
                (organisation_id, survey_2_id, new_program_id),
                method='PUT', body='', expected=200)

        # Duplicate submission, once for each survey, in the new program
        with base.mock_user('org_admin'):
            submission_son = {'title': "Second submission"}
            submission_son = self.fetch(
                "/submission.json?orgId=%s&programId=%s&"
                "surveyId=%s&duplicateId=%s" %
                (organisation_id, new_program_id,
                 survey_1_id, first_submission_id),
                method='POST', body=json_encode(submission_son),
                expected=200, decode=True)
            second_submission_id = submission_son['id']

            submission_son = {'title': "Third submission"}
            submission_son = self.fetch(
                "/submission.json?orgId=%s&programId=%s&"
                "surveyId=%s&duplicateId=%s" %
                (organisation_id, new_program_id,
                 survey_2_id, first_submission_id),
                method='POST', body=json_encode(submission_son),
                expected=200, decode=True)
            third_submission_id = submission_son['id']

        self.assertNotEqual(first_submission_id, second_submission_id)
        self.assertNotEqual(first_submission_id, third_submission_id)
        self.assertNotEqual(second_submission_id, third_submission_id)

        # Check contents
        with model.session_scope() as session:
            submission_1 = (session.query(model.Submission)
                .get(first_submission_id))
            submission_2 = (session.query(model.Submission)
                .get(second_submission_id))
            submission_3 = (session.query(model.Submission)
                .get(third_submission_id))

            self.assertEqual(submission_1.survey_id,
                submission_2.survey_id)
            self.assertNotEqual(submission_1.survey_id,
                submission_3.survey_id)

            # Submission 1 has responses against five measures. Two are
            # descendants of deleted qnodes.
            # Submission 2 uses the same survey as the source submission,
            # so it should have the same number of responses (three, because
            # the deleted ones are not copied).
            # Submission 3 uses a different survey with only one common
            # measure, so it should have a different number of responses (two).
            self.assertEqual(len(submission_1.responses), 5)
            self.assertEqual(len(submission_2.responses), 3)
            self.assertEqual(len(submission_3.responses), 2)
            self.assertEqual(session.query(model.Response).count(), 10)

            # Make sure the number of rnodes matches the number of qnodes in the
            # survey (no leftovers).
            self.assertEqual(session.query(model.ResponseNode)
                .filter_by(submission_id=submission_1.id)
                .count(), 4)
            self.assertEqual(session.query(model.ResponseNode)
                .filter_by(submission_id=submission_2.id)
                .count(), 4)
            self.assertEqual(session.query(model.ResponseNode)
                .filter_by(submission_id=submission_3.id)
                .count(), 3)

            # Check scores. Submissions 1 and 2 should have the same score:
            # 100 + 200 = 300 (due to weighting of the measures). Submission 3
            # should have just 200.
            self.assertEqual([r.score for r in submission_1.ordered_responses],
                             [3, 6, 11])
            self.assertEqual(list(submission_1.rnodes)[0].score, 20)
            self.assertEqual(list(submission_1.rnodes)[1].score, 0)

            self.assertEqual([r.score for r in submission_2.ordered_responses],
                             [3, 6, 11])
            self.assertEqual(list(submission_2.rnodes)[0].score, 20)
            self.assertEqual(list(submission_2.rnodes)[1].score, 0)

            self.assertEqual([r.score for r in submission_3.ordered_responses],
                             [6, 11])
            self.assertEqual(list(submission_3.rnodes)[0].score, 17)
            self.assertEqual(list(submission_3.rnodes)[1].score, 0)

            # When an submission is duplicated, all of its responses are set to
            # 'draft'.
            self.assertEqual(submission_1.approval, 'final')
            self.assertTrue(all(r.approval == 'final'
                                for r in submission_1.responses))
            self.assertEqual(list(submission_1.rnodes)[0].n_draft, 3)
            self.assertEqual(list(submission_1.rnodes)[1].n_draft, 0)
            self.assertEqual(list(submission_1.rnodes)[0].n_final, 3)
            self.assertEqual(list(submission_1.rnodes)[1].n_final, 0)

            self.assertEqual(submission_2.approval, 'draft')
            self.assertTrue(all(r.approval == 'draft'
                                for r in submission_2.responses))
            self.assertEqual(list(submission_2.rnodes)[0].n_draft, 3)
            self.assertEqual(list(submission_2.rnodes)[1].n_draft, 0)
            self.assertEqual(list(submission_2.rnodes)[0].n_final, 0)
            self.assertEqual(list(submission_2.rnodes)[1].n_final, 0)

            self.assertEqual(submission_3.approval, 'draft')
            self.assertTrue(all(r.approval == 'draft'
                                for r in submission_3.responses))
            self.assertEqual(list(submission_3.rnodes)[0].n_draft, 2)
            self.assertEqual(list(submission_3.rnodes)[1].n_draft, 0)
            self.assertEqual(list(submission_3.rnodes)[0].n_final, 0)
            self.assertEqual(list(submission_3.rnodes)[1].n_final, 0)

            # Check attachment duplication
            for r1, r2 in zip(submission_1.ordered_responses,
                              submission_2.ordered_responses):
                self.assertNotEqual(str(r1.id), str(r2.id))
                self.assertEqual(len(r1.attachments), 3)
                self.assertEqual(len(r2.attachments), 3)
                for a1, a2 in zip(r1.attachments, r2.attachments):
                    self.assertNotEqual(str(a1.id), str(a2.id))
                    self.assertEqual(a1.file_name, a2.file_name)
                    self.assertEqual(a1.url, a2.url)
                    self.assertEqual(a1.blob, a2.blob)
