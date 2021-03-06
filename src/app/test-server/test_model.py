import itertools
import logging

import sqlalchemy
from sqlalchemy.orm.session import make_transient
from tornado.escape import json_encode

import base
import model
from score import Calculator


log = logging.getLogger('app.test.test_model')


class ProgramStructureTest(base.AqModelTestBase):

    def test_traverse_structure(self):
        # Read from database
        with model.session_scope() as session:
            program = session.query(model.Program).first()
            self.assertEqual(len(program.surveys), 2)
            self.assertEqual(len(program.measures), 6)
            h = program.surveys[0]
            self.assertEqual(h.title, "Survey 1")
            self.assertEqual(len(h.qnodes), 2)
            self.assertEqual(h.n_measures, 4)

            self.assertEqual(h.qnodes[1].seq, 1)
            q = h.qnodes[0]
            self.assertEqual(q.title, "Function 1")
            self.assertEqual(q.seq, 0)
            self.assertEqual(len(q.children), 2)
            self.assertEqual(len(q.qnode_measures), 0)
            self.assertEqual(q.n_measures, 4)

            q = q.children[0]
            self.assertEqual(q.title, "Process 1.1")
            self.assertEqual(q.seq, 0)
            self.assertEqual(len(q.children), 0)
            self.assertEqual(len(q.qnode_measures), 2)
            self.assertEqual(q.n_measures, 2)

            # Test association from measure to qnode (via qnode_measure)
            self.assertEqual(q.qnode_measures[0].seq, 0)
            self.assertEqual(q.qnode_measures[1].seq, 1)
            m = q.qnode_measures[0].measure
            self.assertEqual(m.title, "Foo Measure")
            self.assertIn(q.qnode_measures[0], m.qnode_measures)
            self.assertEqual(m.qnode_measures[0], q.qnode_measures[0])

    def test_list_measures(self):
        with model.session_scope() as session:
            program = session.query(model.Program).first()
            measures = session.query(model.Measure)\
                .filter(model.Measure.program_id == program.id)\
                .all()
            self.assertEqual(len(measures), 6)

    def test_unlink_measure(self):
        with model.session_scope() as session:
            program = session.query(model.Program).first()
            h = program.surveys[0]
            q = h.qnodes[0].children[0]
            self.assertEqual(len(q.qnode_measures), 2)
            self.assertEqual(q.parent.n_measures, 4)
            self.assertEqual(q.qnode_measures[0].measure.title, "Foo Measure")
            self.assertEqual(q.qnode_measures[0].seq, 0)
            self.assertEqual(q.qnode_measures[1].measure.title, "Bar Measure")
            self.assertEqual(q.qnode_measures[1].seq, 1)
            q.qnode_measures.remove(q.qnode_measures[0])
            calculator = Calculator.structural()
            calculator.mark_qnode_dirty(q)
            calculator.execute()
            # Alter sequence: remove first element, and confirm that sequence
            # numbers update.
            session.flush()
            self.assertEqual(len(q.qnode_measures), 1)
            self.assertEqual(q.qnode_measures[0].measure.title, "Bar Measure")
            self.assertEqual(q.qnode_measures[0].seq, 0)
            self.assertEqual(q.n_measures, 1)
            self.assertEqual(q.parent.n_measures, 3)
            self.assertEqual(h.n_measures, 3)

    def test_orphan_measure(self):
        with model.session_scope() as session:
            program = session.query(model.Program).first()
            q = program.surveys[0].qnodes[0].children[0]
            q.qnode_measures.remove(q.qnode_measures[0])

        # Find orphans using outer join
        with model.session_scope() as session:
            program = session.query(model.Program).first()
            measures = session.query(model.Measure)\
                .outerjoin(model.QnodeMeasure)\
                .filter(model.Measure.program_id == program.id)\
                .filter(model.QnodeMeasure.qnode_id == None)\
                .all()
            self.assertEqual(len(measures), 1)
            m = measures[0]
            self.assertEqual(m.title, "Foo Measure")

        # Find non-orphans using inner join
        with model.session_scope() as session:
            program = session.query(model.Program).first()
            measures = (
                session.query(model.Measure)
                .join(model.QnodeMeasure)
                .filter(model.Measure.program_id == program.id)
                .order_by(model.Measure.title)
                .all())
            self.assertEqual(len(measures), 5)
            m = measures[0]
            self.assertEqual(m.title, "Bar Measure")
            m = measures[1]
            self.assertEqual(m.title, "Baz Measure")

    def test_graph(self):
        with model.session_scope() as session:
            survey = (
                session.query(model.Survey)
                .filter(model.Survey.title == 'Survey 1')
                .first())
            program = survey.program

            def assert_error_free():
                self.assertIs(program.error, None)
                self.assertIs(survey.error, None)
                for fn in survey.qnodes:
                    self.assertIs(fn.error, None)
                    for proc in fn.children:
                        self.assertIs(proc.error, None)
                        for qm in proc.qnode_measures:
                            self.assertIs(qm.error, None)

            assert_error_free()

            qnode_measure_111 = survey.qnodes[0].children[0].qnode_measures[0]
            qnode_measure_112 = survey.qnodes[0].children[0].qnode_measures[1]
            qnode_measure_121 = survey.qnodes[0].children[1].qnode_measures[0]
            qnode_measure_122 = survey.qnodes[0].children[1].qnode_measures[1]

            self.assertEqual(0, len(qnode_measure_111.target_vars))
            self.assertEqual(0, len(qnode_measure_111.source_vars))
            self.assertEqual(0, len(qnode_measure_112.target_vars))
            self.assertEqual(0, len(qnode_measure_112.source_vars))
            self.assertEqual(1, len(qnode_measure_121.target_vars))
            self.assertEqual(0, len(qnode_measure_121.source_vars))
            self.assertEqual(0, len(qnode_measure_122.target_vars))
            self.assertEqual(1, len(qnode_measure_122.source_vars))

            # Make measure 1 a dependency (source) of measure 2 (target)
            mv = model.MeasureVariable(
                program=program, survey=survey,
                source_qnode_measure=qnode_measure_111, source_field='foo',
                target_qnode_measure=qnode_measure_112, target_field='ext')
            session.add(mv)
            # session.flush()

            # Check that relationships have updated
            self.assertEqual(1, len(qnode_measure_111.target_vars))
            self.assertEqual(0, len(qnode_measure_111.source_vars))
            self.assertEqual(0, len(qnode_measure_112.target_vars))
            self.assertEqual(1, len(qnode_measure_112.source_vars))
            self.assertEqual(1, len(qnode_measure_121.target_vars))
            self.assertEqual(0, len(qnode_measure_121.source_vars))
            self.assertEqual(0, len(qnode_measure_122.target_vars))
            self.assertEqual(1, len(qnode_measure_122.source_vars))

            # Check that dependency is marked as superfluous (because it's not
            # required by the response type)
            calculator = Calculator.structural()
            calculator.mark_measure_dirty(qnode_measure_111)
            calculator.execute()
            self.assertIn('superfluous', qnode_measure_112.error.lower())

            # Add response type that uses the connection, but which declares
            # a different variable ('a' instead of 'foo')
            ext_response_type = model.ResponseType(
                program=program,
                name="External",
                parts=[{"id": "a", "type": "numerical"}],
                formula="a / ext")
            session.add(ext_response_type)
            qnode_measure_112.measure.response_type = ext_response_type
            # session.flush()
            calculator = Calculator.structural()
            calculator.mark_measure_dirty(qnode_measure_112)
            calculator.execute()
            self.assertIn("doesn't declare", qnode_measure_112.error.lower())

            # Change the binding to the right field
            mv.source_field = 'a'
            calculator = Calculator.structural()
            calculator.mark_measure_dirty(qnode_measure_112)
            calculator.execute()
            assert_error_free()

            # Configure measure to have an unbound variable
            qnode_measure_111.measure.response_type = ext_response_type
            calculator = Calculator.structural()
            calculator.mark_measure_dirty(qnode_measure_111)
            calculator.execute()
            self.assertIn('unbound', qnode_measure_111.error.lower())

            # Make measure 2 a dependency (source) of measure 1 (target)
            mv = model.MeasureVariable(
                program=program, survey=survey,
                source_qnode_measure=qnode_measure_112, source_field='a',
                target_qnode_measure=qnode_measure_111, target_field='ext')
            session.add(mv)
            # session.flush()

            # Check that relationships have updated
            self.assertEqual(1, len(qnode_measure_111.target_vars))
            self.assertEqual(1, len(qnode_measure_111.source_vars))
            self.assertEqual(1, len(qnode_measure_112.target_vars))
            self.assertEqual(1, len(qnode_measure_112.source_vars))
            self.assertEqual(1, len(qnode_measure_121.target_vars))
            self.assertEqual(0, len(qnode_measure_121.source_vars))
            self.assertEqual(0, len(qnode_measure_122.target_vars))
            self.assertEqual(1, len(qnode_measure_122.source_vars))

            # Check that survey graph is constructed correctly
            calculator = Calculator.structural()
            calculator.mark_measure_dirty(qnode_measure_112)
            calculator.execute()
            self.assertIn('cyclic', qnode_measure_111.error.lower())
            self.assertIn('cyclic', qnode_measure_112.error.lower())
            self.assertIn('cyclic', qnode_measure_111.qnode.error.lower())
            self.assertIn(
                'cyclic', qnode_measure_111.qnode.parent.error.lower())
            self.assertIn('cyclic', survey.error.lower())
            self.assertIn('cyclic', program.error.lower())
            self.assertIs(qnode_measure_121.error, None)
            self.assertIs(qnode_measure_121.qnode.error, None)

    def test_history(self):
        # Duplicate a couple of objects
        with model.session_scope() as session:
            program = session.query(model.Program).first()
            survey = program.surveys[0]
            session.expunge(program)
            make_transient(program)
            session.expunge(survey)
            make_transient(survey)

            program.id = None
            program.created = None
            program.title = 'Duplicate program'
            session.add(program)
            session.flush()

            survey.title = 'Duplicate survey'
            survey.program = program

        # Make sure survey ID is still the same
        with model.session_scope() as session:
            programs = session.query(model.Program).all()
            self.assertNotEqual(programs[0].id, programs[1].id)
            self.assertNotEqual(
                programs[0].surveys[0].program_id,
                programs[1].surveys[0].program_id)
            self.assertEqual(
                programs[0].surveys[0].id,
                programs[1].surveys[0].id)

        # Get all programs for some survey ID
        with model.session_scope() as session:
            # This survey was duplicated, and should be in two programs.
            survey = (
                session.query(model.Survey)
                .filter_by(title="Survey 1")
                .one())
            programs = (
                session.query(model.Program)
                .join(model.Survey)
                .filter(model.Survey.id == survey.id)
                .all())
            titles = {s.title for s in programs}
            self.assertEqual(titles, {"Duplicate program", "Test Program 1"})

            # This one was not, so it should only be in the first.
            survey = (
                session.query(model.Survey)
                .filter_by(title="Survey 2")
                .one())
            programs = (
                session.query(model.Program)
                .join(model.Survey)
                .filter(model.Survey.id == survey.id)
                .all())
            titles = {s.title for s in programs}
            self.assertEqual(titles, {"Test Program 1"})


class ProgramTest(base.AqHttpTestBase):

    def test_list_programs(self):
        with base.mock_user('clerk'):
            program_sons = self.fetch(
                "/program.json", method='GET',
                expected=200, decode=True)
            self.assertEqual(len(program_sons), 1)

            program_sons = self.fetch(
                "/program.json?editable=true", method='GET',
                expected=200, decode=True)
            self.assertEqual(len(program_sons), 1)

    def test_basic_query(self):
        with model.session_scope() as session:
            program = session.query(model.Program).first()
            h = program.surveys[0]
            sid = str(program.id)
            hid = str(h.id)

        with base.mock_user('author'):
            # Query for qnodes based on deletion
            url = "/qnode.json?programId={}&surveyId={}".format(sid, hid)
            q_son = self.fetch(
                url,
                method='GET', expected=200, decode=True)
            self.assertEqual(len(q_son), 10)
            q_son = self.fetch(
                url + "&deleted=false",
                method='GET', expected=200, decode=True)
            self.assertEqual(len(q_son), 6)
            q_son = self.fetch(
                url + "&deleted=true",
                method='GET', expected=200, decode=True)
            self.assertEqual(len(q_son), 4)

            # Query for qnodes based on deletion again, this time taking
            # parents into account.
            url += "&level=1"
            q_son = self.fetch(
                url,
                method='GET', expected=200, decode=True)
            self.assertEqual(len(q_son), 6)
            q_son = self.fetch(
                url + "&deleted=false",
                method='GET', expected=200, decode=True)
            self.assertEqual(len(q_son), 2)
            q_son = self.fetch(
                url + "&deleted=true",
                method='GET', expected=200, decode=True)
            self.assertEqual(len(q_son), 4)


class ModifyProgramTest(base.AqHttpTestBase):

    def setUp(self):
        super().setUp()
        with model.session_scope() as session:
            program = session.query(model.Program).first()
            h = [h for h in program.surveys if h.title == "Survey 1"][0]
            qA, qB = h.qnodes
            qAA, qAB = qA.children
            self.sid = str(program.id)
            self.hid = str(h.id)
            self.qidA, self.qidB, self.qidAA, self.qidAB = [
                str(q.id) for q in (qA, qB, qAA, qAB)]
            self.midAAA = str(qAA.qnode_measures[0].measure_id)
            self.midAAB = str(qAA.qnode_measures[1].measure_id)
            self.midABA = str(qAB.qnode_measures[0].measure_id)
            user = (session.query(model.AppUser)
                    .filter_by(email='author')
                    .one())
            self.organisation_id = str(user.organisation.id)

        with base.mock_user('admin'):
            # need to purchase survey
            self.purchase_program(self.hid, self.sid)

    def verify_stats(self):
        # Make sure stats match reality

        def qnodes(roots):
            # All qnodes in a tree (flattened list, depth-first)
            for root in roots:
                yield root
                for q in qnodes(root.children):
                    yield q

        def measures(roots):
            # All measures under a qnode
            for qn in qnodes(roots):
                for qm in qn.qnode_measures:
                    yield qm.measure

        with model.session_scope() as session:
            surveys = (
                session.query(model.Survey)
                .filter(model.Survey.deleted == False)
                .all())
            for h in surveys:
                for q in qnodes(h.qnodes):
                    n_measures = len(list(measures([q])))
                    weight = sum(m.weight for m in measures([q]))
                    log.debug(
                        "%s - N: actual: %d, cached: %d", q.title,
                        n_measures, q.n_measures)
                    log.debug(
                        "%s - W: actual: %d, cached: %d", q.title,
                        weight, q.total_weight)
                    self.assertEqual(n_measures, q.n_measures, q.title)
                    self.assertEqual(weight, q.total_weight, q.title)

    def test_unmodified_structure(self):
        self.verify_stats()
        with base.mock_user('author'):
            # Check current weights of qnode and measure
            q2_son = self.fetch(
                "/qnode/{}.json?programId={}".format(self.qidAB, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q2_son['total_weight'], 11 + 13)
            m_son = self.fetch(
                "/measure/{}.json?programId={}".format(self.midABA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(m_son['weight'], 11)
            self.assertIn(self.qidAB, (p['id'] for p in m_son['parents']))
            self.assertNotIn(self.qidAA, (p['id'] for p in m_son['parents']))

    def test_modify_weight(self):
        with base.mock_user('author'):
            # Modify a measure's weight and check that the qnode weight is
            # updated
            m_son = self.fetch(
                "/measure/{}.json?programId={}".format(self.midAAA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(m_son['weight'], 3)
            m_son['weight'] = 9
            m_son = self.fetch(
                "/measure/{}.json?programId={}".format(self.midAAA, self.sid),
                method='PUT', body=json_encode(m_son),
                expected=200, decode=True)
            self.assertAlmostEqual(m_son['weight'], 9)
            q_son = self.fetch(
                "/qnode/{}.json?programId={}".format(self.qidAA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q_son['total_weight'], 15)
        self.verify_stats()

    def test_measure_move(self):
        with base.mock_user('author'):
            # Move measure to different parent and check that weights have
            # moved
            m_son = self.fetch(
                "/measure/{}.json?programId={}&parentId={}".format(
                    self.midABA, self.sid, self.qidAA),
                method='PUT', body=json_encode({}),
                expected=200, decode=True)
            self.assertIn(self.qidAA, (p['id'] for p in m_son['parents']))
            self.assertNotIn(self.qidAB, (p['id'] for p in m_son['parents']))
            q_son = self.fetch(
                "/qnode/{}.json?programId={}".format(self.qidAA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q_son['total_weight'], 20)
            q2_son = self.fetch(
                "/qnode/{}.json?programId={}".format(self.qidAB, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q2_son['total_weight'], 13)
        self.verify_stats()

    def test_delete_qnode(self):
        with base.mock_user('author'):
            # Delete a qnode and check that the parent weight is updated
            self.fetch(
                "/qnode/{}.json?programId={}".format(self.qidAA, self.sid),
                method='DELETE', expected=200)
            q_son = self.fetch(
                "/qnode/{}.json?programId={}".format(self.qidA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q_son['total_weight'], 11 + 13)

            # Check that a measure is still writable
            self.fetch(
                "/measure/{}.json?programId={}&parentId={}".format(
                    self.midAAA, self.sid, self.qidB),
                method='PUT', body=json_encode({}),
                expected=200, decode=True)

            # Move a measure out of the deleted qnode...
            q_son = self.fetch(
                "/qnode/{}.json?programId={}".format(self.qidA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q_son['total_weight'], 11 + 13)
            q_son = self.fetch(
                "/qnode/{}.json?programId={}".format(self.qidB, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q_son['total_weight'], 3)

            self.verify_stats()

            # Undelete the qnode
            self.fetch(
                "/qnode/{}.json?programId={}".format(self.qidAA, self.sid),
                method='PUT', body=json_encode({}), expected=200)
            q_son = self.fetch(
                "/qnode/{}.json?programId={}".format(self.qidA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q_son['total_weight'], 6 + 11 + 13)

            self.verify_stats()

    def test_delete_measure(self):
        with base.mock_user('author'):
            # Delete a measure and check that the qnode weight is updated
            self.fetch(
                "/measure/{}.json?programId={}&parentId={}".format(
                    self.midAAA, self.sid, self.qidAA),
                method='DELETE', expected=200)
            q_son = self.fetch(
                "/qnode/{}.json?programId={}".format(self.qidAA, self.sid),
                method='GET', expected=200, decode=True)
            self.assertAlmostEqual(q_son['total_weight'], 6)

        self.verify_stats()

    def test_duplicate_program(self):
        with base.mock_user('author'):
            program_sons = self.fetch(
                "/program.json?term=Test%%20Program%%201", method='GET',
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
            self.assertNotEqual(original_program_id, new_program_id)

            def check_surveys():
                # Check duplicated surveys
                original_survey_sons = self.fetch(
                    "/survey.json?programId=%s" % original_program_id,
                    method='GET',
                    expected=200, decode=True)

                new_survey_sons = self.fetch(
                    "/survey.json?programId=%s" % new_program_id, method='GET',
                    expected=200, decode=True)

                for h1, h2 in zip(original_survey_sons, new_survey_sons):
                    self.assertEqual(h1['id'], h2['id'])
                    self.assertEqual(h1['title'], h2['title'])
                    check_qnodes(h1['id'], '')

            def check_qnodes(survey_id, parent_id):
                with base.mock_user('admin'):
                    self.purchase_program(survey_id, original_program_id)
                    self.purchase_program(survey_id, new_program_id)

                with base.mock_user('author'):
                    # Check duplicated qnodes
                    url = ("/qnode.json?programId=%s&surveyId=%s&parentId=%s"
                           "&deleted=false")
                    if not parent_id:
                        url += '&root='
                    url1 = url % (original_program_id, survey_id, parent_id)
                    url2 = url % (new_program_id, survey_id, parent_id)
                    original_qnode_sons = self.fetch(
                        url1, method='GET', expected=200, decode=True)
                    new_qnode_sons = self.fetch(
                        url2, method='GET', expected=200, decode=True)

                    log.info(("URL 1: %s\n" % url1) + ("URL 2: %s" % url2))
                    for q1, q2 in zip(original_qnode_sons, new_qnode_sons):
                        log.info("q1: %s, q2: %s", q1, q2)
                        self.assertEqual(q1['id'], q2['id'])
                        self.assertEqual(q1['title'], q2['title'])
                        check_qnodes(survey_id, q1['id'])
                        check_measures(q1['id'])

            def check_measures(parent_id):
                # Check duplicated measures
                url = "/measure.json?programId=%s&parentId=%s"
                original_measure_sons = self.fetch(
                    url % (original_program_id, parent_id), method='GET',
                    expected=200, decode=True)
                new_measure_sons = self.fetch(
                    url % (new_program_id, parent_id), method='GET',
                    expected=200, decode=True)

                for m1, m2 in zip(original_measure_sons, new_measure_sons):
                    self.assertEqual(m1['id'], m2['id'])
                    self.assertEqual(m1['title'], m2['title'])

            check_measures('')
            check_surveys()

        # Thoroughly test new relationships: make sure there is no
        # cross-referencing between new and old program.
        with model.session_scope() as session:
            sa = session.query(model.Program).get(original_program_id)
            sb = session.query(model.Program).get(new_program_id)
            self.assertNotEqual(sa.id, sb.id)
            self.assertEqual(sa.tracking_id, sb.tracking_id)
            self.assertNotEqual(sa, sb)
            log.info("Visiting program pair %s and %s", sa, sb)

            def visit_survey(a, b):
                log.info("Visiting survey pair %s and %s", a, b)
                self.assertEqual(a.id, b.id)
                self.assertNotEqual(a, b)

                self.assertEqual(a.program_id, sa.id)
                self.assertEqual(b.program_id, sb.id)
                self.assertEqual(a.program, sa)
                self.assertEqual(b.program, sb)

                self.assertEqual(len(a.qnodes), len(b.qnodes))
                for qa, qb in zip(a.qnodes, b.qnodes):
                    visit_qnode(qa, qb, a, b, None, None)

            def visit_qnode(a, b, ha, hb, pa, pb):
                log.info("Visiting qnode pair %s and %s", a, b)
                self.assertEqual(a.id, b.id)
                self.assertNotEqual(a, b)
                self.assertEqual(a.survey_id, b.survey_id)

                self.assertEqual(a.program_id, sa.id)
                self.assertEqual(b.program_id, sb.id)
                self.assertEqual(a.program, sa)
                self.assertEqual(b.program, sb)

                self.assertEqual(a.survey_id, ha.id)
                self.assertEqual(b.survey_id, hb.id)
                self.assertEqual(a.survey, ha)
                self.assertEqual(b.survey, hb)

                if pa is not None:
                    self.assertEqual(a.parent_id, pa.id)
                    self.assertEqual(b.parent_id, pb.id)
                self.assertEqual(a.parent, pa)
                self.assertEqual(b.parent, pb)

                self.assertEqual(len(a.children), len(b.children))
                for qa, qb in zip(a.children, b.children):
                    visit_qnode(qa, qb, ha, hb, a, b)

                self.assertEqual(len(a.qnode_measures), len(b.qnode_measures))
                for qma, qmb in zip(a.qnode_measures, b.qnode_measures):
                    visit_qnode_measure(qma, qmb, a, b)

            def visit_qnode_measure(a, b, qa, qb):
                log.info("Visiting qnode_measure pair %s and %s", a, b)
                self.assertEqual(a.qnode_id, b.qnode_id)
                self.assertEqual(a.measure_id, b.measure_id)
                self.assertNotEqual(a.measure, b.measure)

                self.assertEqual(a.program_id, sa.id)
                self.assertEqual(b.program_id, sb.id)
                self.assertEqual(a.program, sa)
                self.assertEqual(b.program, sb)

                self.assertEqual(a.qnode_id, qa.id)
                self.assertEqual(b.qnode_id, qb.id)
                self.assertEqual(a.qnode, qa)
                self.assertEqual(b.qnode, qb)

                for mva, mvb in itertools.zip_longest(
                        a.source_vars, b.source_vars):
                    visit_var(mva, mvb)

                for mva, mvb in itertools.zip_longest(
                        a.target_vars, b.target_vars):
                    visit_var(mva, mvb)

                visit_measure(a.measure, b.measure, a, b)

            def visit_var(mva, mvb):
                self.assertNotEqual(mva, None)
                self.assertNotEqual(mvb, None)
                self.assertEqual(str(mva.program_id), original_program_id)
                self.assertEqual(str(mvb.program_id), new_program_id)
                self.assertEqual(mva.survey_id, mvb.survey_id)
                self.assertEqual(mva.source_measure_id, mvb.source_measure_id)
                self.assertEqual(mva.source_field, mvb.source_field)
                self.assertEqual(mva.target_measure_id, mvb.target_measure_id)
                self.assertEqual(mva.target_field, mvb.target_field)

            def visit_measure(a, b, qma, qmb):
                log.info("Visiting measure pair %s and %s", a, b)
                self.assertEqual(a.id, b.id)
                self.assertNotEqual(a, b)

                self.assertEqual(a.program_id, sa.id)
                self.assertEqual(b.program_id, sb.id)
                self.assertEqual(a.program, sa)
                self.assertEqual(b.program, sb)

                if qma is not None:
                    self.assertIn(qma, a.qnode_measures)
                    self.assertNotIn(qma, b.qnode_measures)
                    self.assertIn(qmb, b.qnode_measures)
                    self.assertNotIn(qmb, a.qnode_measures)

            # A has five measures, but two are only referenced by deleted
            # nodes.
            self.assertEqual(len(sa.measures), 6)
            self.assertEqual(len(sb.measures), 4)
            measures_in_a = {m.id: m for m in sa.measures}
            for b in sb.measures:
                a = measures_in_a[b.id]
                visit_measure(a, b, None, None)

            # A has three surveys, but one is deleted.
            self.assertEqual(len(sa.surveys), 2)
            self.assertEqual(len(sb.surveys), 2)
            for a, b in zip(sa.surveys, sb.surveys):
                visit_survey(a, b)
        self.verify_stats()

    def purchase_program(self, survey_id, program_id):
        with model.session_scope() as session:
            user = (
                session.query(model.AppUser)
                .filter_by(email='admin')
                .one())
            organisation_id = str(user.organisation.id)

            self.fetch(
                "/organisation/%s/survey/%s.json?programId=%s" %
                (organisation_id, survey_id, program_id),
                method='PUT', body='', expected=200)


class ResponseTypeTest(base.AqHttpTestBase):

    def test_get(self):
        with model.session_scope() as session:
            survey = (
                session.query(model.Survey)
                .filter(model.Survey.title == 'Survey 1')
                .first())
            pid = str(survey.program_id)

        with base.mock_user('clerk'):
            rts = self.fetch(
                "/response_type.json?programId=%s" % pid,
                method='GET', expected=200, decode=True)
            self.assertGreater(len(rts), 1)
            self.assertIn('Yes / No', (rt['name'] for rt in rts))

            rts = self.fetch(
                "/response_type.json?programId=%s&term=Yes%%20/%%20No" % pid,
                method='GET', expected=200, decode=True)
            self.assertEqual(len(rts), 1)
            self.assertEqual('Yes / No', rts[0]['name'])
            self.assertEqual(3, rts[0]['n_measures'])

            rt_id = rts[0]['id']
            rt = self.fetch(
                "/response_type/%s.json?programId=%s" % (rt_id, pid),
                method='GET', expected=200, decode=True)
            self.assertEqual([
                {
                    "id": "a",
                    "type": "multiple_choice",
                    "options": [
                        {"score": 0.0, "name": "No"},
                        {"score": 1.0, "name": "Yes"}
                    ],
                }
            ], rt['parts'])

            self.fetch(
                "/response_type/%s.json?programId=%s" % (rt_id, pid),
                method='DELETE', expected=403)

            rts = self.fetch(
                "/response_type.json?programId=%s&term=Numerical" % pid,
                method='GET', expected=200, decode=True)
            self.assertEqual(len(rts), 1)
            self.assertEqual('Numerical', rts[0]['name'])
            self.assertEqual(1, rts[0]['n_measures'])

    def test_modify(self):
        with model.session_scope() as session:
            survey = session.query(model.Survey).first()
            pid = str(survey.program_id)
            mtime = survey.modified

        # Save an RT with no modifications
        with base.mock_user('author'):
            rt = self.fetch(
                "/response_type.json?programId=%s&term=Yes%%20/%%20No" % pid,
                method='GET', expected=200, decode=True)[0]
            rt = self.fetch(
                "/response_type/%s.json?programId=%s" % (rt['id'], pid),
                method='PUT', expected=200, body=rt, decode=True)

        with model.session_scope() as session:
            survey = session.query(model.Survey).first()
            self.assertEqual(survey.modified, mtime)

        # Modify an RT and check that it updates the survey appropriately
        with base.mock_user('author'):
            rt['parts'][0]['options'].append({'name': 'Oh yes', 'score': 2.0})
            rt = self.fetch(
                "/response_type/%s.json?programId=%s" % (rt['id'], pid),
                method='PUT', expected=200, body=rt, decode=True)

        with model.session_scope() as session:
            survey = session.query(model.Survey).first()
            self.assertGreater(survey.modified, mtime)

    def test_authz(self):
        with model.session_scope() as session:
            survey = (
                session.query(model.Survey)
                .filter(model.Survey.title == 'Survey 1')
                .first())
            pid = str(survey.program_id)

        # Create a new RT and check that it can only be modified by an author
        with base.mock_user('author'):
            rt = self.fetch(
                "/response_type.json?programId=%s" % (pid),
                method='POST', expected=200, body={
                    'name': "Test RT",
                    'parts': []
                }, decode=True)
            self.assertEqual(0, rt['n_measures'])
            rt_id = rt['id']
            rt = self.fetch(
                "/response_type/%s.json?programId=%s" % (rt_id, pid),
                method='PUT', expected=200, body=rt, decode=True)

        with base.mock_user('clerk'):
            self.fetch(
                "/response_type/%s.json?programId=%s" % (rt_id, pid),
                method='PUT', expected=403, body=rt)
            self.fetch(
                "/response_type.json?programId=%s" % (pid),
                method='POST', expected=403, body={
                    'name': "Test RT",
                    'parts': []
                })
            self.fetch(
                "/response_type/%s.json?programId=%s" % (rt_id, pid),
                method='DELETE', expected=403)

        with base.mock_user('author'):
            rts1 = self.fetch(
                "/response_type.json?programId=%s" % pid,
                method='GET', expected=200, decode=True)
            self.assertIn('Test RT', [rt['name'] for rt in rts1])
            self.fetch(
                "/response_type/%s.json?programId=%s" % (rt_id, pid),
                method='DELETE', expected=200)
            rts2 = self.fetch(
                "/response_type.json?programId=%s" % pid,
                method='GET', expected=200, decode=True)
            self.assertEqual(len(rts1), len(rts2) + 1)
            self.assertNotIn('Test RT', (rt['name'] for rt in rts2))


class ReadonlySessionTest(base.AqModelTestBase):

    def test_readonly_session(self):
        with model.session_scope(readonly=True) as session:
            programs = session.query(model.Program).all()
            self.assertNotEqual(len(programs), 0)

        with self.assertRaises(sqlalchemy.exc.ProgrammingError) as ecm, \
                model.session_scope(readonly=True) as session:
            session.query(model.SystemConfig).all()
        self.assertIn('permission denied', str(ecm.exception))

        with self.assertRaises(sqlalchemy.exc.ProgrammingError) as ecm, \
                model.session_scope(readonly=True) as session:
            session.execute("DELETE FROM measure")
        self.assertIn('permission denied', str(ecm.exception))

        with self.assertRaises(sqlalchemy.exc.ProgrammingError) as ecm, \
                model.session_scope(readonly=True) as session:
            session.execute("UPDATE measure SET title = 'foo'")
        self.assertIn('permission denied', str(ecm.exception))

        with self.assertRaises(sqlalchemy.exc.ProgrammingError) as ecm, \
                model.session_scope(readonly=True) as session:
            item = model.Measure(title='FOo')
            session.add(item)
        self.assertIn('permission denied', str(ecm.exception))
