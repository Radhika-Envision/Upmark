from concurrent.futures import ThreadPoolExecutor
import json
import time

import sqlalchemy
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import literal
from tornado import gen
from tornado.escape import json_encode
import tornado.web
from tornado.concurrent import run_on_executor

import base_handler
import errors
import model
import logging

from utils import ToSon


MAX_WORKERS = 4

log = logging.getLogger('app.report.diff')


perf_time = time.perf_counter()
perf_start = None
def perf():
    global perf_start, perf_time
    if perf_start is None:
        perf_start = time.perf_counter()
        perf_time = 0.0
    else:
        now = time.perf_counter()
        perf_time += now - perf_start
        perf_start = now
    return perf_time


class DiffHandler(base_handler.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def get(self):
        program_id_a = self.get_argument("programId1", '')
        program_id_b = self.get_argument("programId2", '')
        survey_id = self.get_argument("surveyId", '')

        ignore_tags = set().union(self.get_arguments("ignoreTag"))

        if program_id_a == '':
            raise errors.ModelError("Program ID 1 required")
        if program_id_b == '':
            raise errors.ModelError("Program ID 2 required")
        if survey_id == '':
            raise errors.ModelError("Survey ID required")

        include_scores = self.current_user.role != 'clerk'

        son, details = yield self.background_task(
            program_id_a, program_id_b, survey_id, ignore_tags, include_scores)

        for i, message in enumerate(details):
            self.add_header('Profiling', "%d %s" % (i, message))

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @run_on_executor
    def background_task(
            self, program_id_a, program_id_b, survey_id, ignore_tags,
            include_scores):

        with model.session_scope() as session:
            self.check_browse_program(session, program_id_a, survey_id)
            self.check_browse_program(session, program_id_b, survey_id)

            diff_engine = DiffEngine(
                session, program_id_a, program_id_b, survey_id, include_scores)
            diff = diff_engine.execute()
            diff = [di for di in diff
                    if len(set().union(di['tags']).difference(ignore_tags)) > 0]
            son = {
                'diff': diff
            }
        return son, diff_engine.timing


class DiffEngine:
    def __init__(self, session, program_id_a, program_id_b, survey_id,
                 include_scores=True):
        self.session = session
        self.program_id_a = program_id_a
        self.program_id_b = program_id_b
        self.survey_id = survey_id
        self.include_scores = include_scores
        self.timing = []

    def execute(self):
        qnode_pairs = self.get_qnodes()
        measure_pairs = self.get_measures()

        to_son = ToSon(
            r'/id$',
            r'/survey_id$',
            r'/parent_id$',
            r'/title$',
            r'</description$',
            r'/response_type_id$',
            r'/seq$',
            # Descend
            r'/[0-9]+$',
            r'^/[0-9]+/[^/]+$',
        )

        if self.include_scores:
            to_son.add(
                r'/weight$',
            )

        qnode_pairs = self.realise_soft_deletion(qnode_pairs)
        qnode_pairs = self.remove_soft_deletion_dups(qnode_pairs)
        qnode_diff = [{
                'type': 'qnode',
                'tags': [],
                'pair': pair,
            } for pair in to_son(qnode_pairs)]
        start = perf()
        self.add_qnode_metadata(qnode_pairs, qnode_diff)
        self.add_metadata(qnode_pairs, qnode_diff)
        duration = perf() - start
        self.timing.append("Qnode metadata took %gs" % duration)
        self.remove_unchanged_fields(qnode_diff)

        measure_pairs = self.realise_soft_deletion(measure_pairs)
        measure_pairs = self.remove_soft_deletion_dups(measure_pairs)
        measure_diff = [{
                'type': 'measure',
                'tags': [],
                'pair': pair,
            } for pair in to_son(measure_pairs)]
        start = perf()
        self.add_measure_metadata(measure_pairs, measure_diff)
        self.add_metadata(measure_pairs, measure_diff)
        duration = perf() - start
        self.timing.append("Measure metadata took %gs" % duration)
        self.remove_unchanged_fields(measure_diff)

        diff = qnode_diff + measure_diff

        def path_key(diff_item):
            a, b = diff_item['pair']
            if a and b:
                return 0, [int(c) for c in b['path'].split('.') if c != '']
            elif b:
                return 0, [int(c) for c in b['path'].split('.') if c != '']
            elif a:
                return 1, [int(c) for c in a['path'].split('.') if c != '']
            else:
                return 2
        start = perf()
        diff.sort(key=path_key)
        duration = perf() - start
        self.timing.append("Sorting took %gs" % duration)

        HA = model.Survey
        HB = aliased(model.Survey, name='survey_b')
        survey_a, survey_b = (self.session.query(HA, HB)
            .join(HB, (HA.id == HB.id))
            .filter(HA.program_id == self.program_id_a,
                    HB.program_id == self.program_id_b,
                    HA.id == self.survey_id)
            .first())
        to_son = ToSon(
            r'/id$',
            r'/title$',
            r'</description$',
        )
        top_level_diff = [
            {
                'type': 'program',
                'tags': ['context'],
                'pair': [to_son(survey_a.program), to_son(survey_b.program)]
            },
            {
                'type': 'survey',
                'tags': ['context'],
                'pair': [to_son(survey_a), to_son(survey_b)]
            }
        ]
        self.remove_unchanged_fields(top_level_diff)

        return top_level_diff + diff

    def get_qnodes(self):
        QA = model.QuestionNode
        QB = aliased(model.QuestionNode, name='qnode_b')

        start = perf()

        # Find modified / relocated qnodes
        qnode_mod_query = (self.session.query(QA, QB)
            .join(QB, QA.id == QB.id)

            # Basic survey membership
            .filter(QA.program_id == self.program_id_a,
                    QB.program_id == self.program_id_b,
                    QA.survey_id == self.survey_id,
                    QB.survey_id == self.survey_id)

            # Filter for modified objects
            .filter((QA.title != QB.title) |
                    (QA.description != QB.description) |
                    (QA.parent_id != QB.parent_id) |
                    (QA.seq != QB.seq))
        )

        # Find deleted qnodes
        qnode_del_query = (self.session.query(QA, literal(None))
            .select_from(QA)
            .filter(QA.program_id == self.program_id_a,
                    QA.survey_id == self.survey_id,
                    ~QA.id.in_(
                        self.session.query(QB.id)
                            .filter(QB.program_id == self.program_id_b,
                                    QB.survey_id == self.survey_id,
                                    QB.deleted == False)))
        )

        # Find added qnodes
        qnode_add_query = (self.session.query(literal(None), QB)
            .select_from(QB)
            .filter(QB.program_id == self.program_id_b,
                    QB.survey_id == self.survey_id,
                    ~QB.id.in_(
                        self.session.query(QA.id)
                            .filter(QA.program_id == self.program_id_a,
                                    QA.survey_id == self.survey_id,
                                    QA.deleted == False)))
        )

        qnodes = list(qnode_mod_query.all()
                    + qnode_add_query.all()
                    + qnode_del_query.all())
        duration = perf() - start
        self.timing.append("Primary qnode query took %gs" % duration)
        return qnodes

    def get_measures(self):
        QA = model.QuestionNode
        QB = aliased(model.QuestionNode, name='qnode_b')
        MA = model.Measure
        MB = aliased(model.Measure, name='measure_b')
        QMA = model.QnodeMeasure
        QMB = aliased(model.QnodeMeasure, name='qnode_measure_b')

        start = perf()

        # Find modified / relocated measures
        measure_mod_query = (self.session.query(MA, MB)

            .join(MB, MA.id == MB.id)

            .join(QMA,
                  (QMA.program_id == MA.program_id) &
                  (QMA.measure_id == MA.id))
            .join(QMB,
                  (QMB.program_id == MB.program_id) &
                  (QMB.measure_id == MB.id))
            .join(QA,
                  (QMA.program_id == QA.program_id) &
                  (QMA.qnode_id == QA.id))
            .join(QB,
                  (QMB.program_id == QB.program_id) &
                  (QMB.qnode_id == QB.id))

            # Basic survey membership
            .filter(QA.program_id == self.program_id_a,
                    QB.program_id == self.program_id_b,
                    QA.survey_id == self.survey_id,
                    QB.survey_id == self.survey_id)

            # Filter for modified objects
            .filter((MA.title != MB.title) |
                    (MA.description != MB.description) |
                    (MA.response_type_id != MB.response_type_id) |
                    (MA.weight != MB.weight) |
                    (QMA.qnode_id != QMB.qnode_id) |
                    (QMA.seq != QMB.seq))
        )

        # Find deleted measures
        measure_del_query = (self.session.query(MA, literal(None))
            .select_from(MA)
            .join(QMA,
                  (QMA.program_id == MA.program_id) &
                  (QMA.measure_id == MA.id))
            .join(QA,
                  (QMA.program_id == QA.program_id) &
                  (QMA.qnode_id == QA.id))
            .filter(QA.program_id == self.program_id_a,
                    QA.survey_id == self.survey_id,
                    ~QMA.measure_id.in_(
                        self.session.query(QMB.measure_id)
                            .join(QB,
                                  (QMB.program_id == QB.program_id) &
                                  (QMB.qnode_id == QB.id))
                            .filter(QB.program_id == self.program_id_b,
                                    QB.survey_id == self.survey_id)))
        )

        # Find added measures
        measure_add_query = (self.session.query(literal(None), MB)
            .select_from(MB)
            .join(QMB,
                  (QMB.program_id == MB.program_id) &
                  (QMB.measure_id == MB.id))
            .join(QB,
                  (QMB.program_id == QB.program_id) &
                  (QMB.qnode_id == QB.id))
            .filter(QB.program_id == self.program_id_b,
                    QB.survey_id == self.survey_id,
                    ~QMB.measure_id.in_(
                        self.session.query(QMA.measure_id)
                            .join(QA,
                                  (QMA.program_id == QA.program_id) &
                                  (QMA.qnode_id == QA.id))
                            .filter(QA.program_id == self.program_id_a,
                                    QA.survey_id == self.survey_id)))
        )

        measures = list(measure_mod_query.all()
                    + measure_add_query.all()
                    + measure_del_query.all())
        duration = perf() - start
        self.timing.append("Primary measure query took %gs" % duration)
        return measures

    def realise_soft_deletion(self, pairs):
        def realise(x):
            if not x:
                return None

            if hasattr(x, 'get_qnode_measure'):
                # measure
                if x.deleted:
                    return None
                q = x.get_qnode_measure(self.survey_id).qnode
            else:
                # qnode
                q = x

            deleted_ancestor = q.closest_deleted_ancestor()
            if deleted_ancestor is not None:
                if deleted_ancestor.ob_type not in {'program', 'survey'}:
                    return None

            return x

        return [(realise(a), realise(b)) for (a, b) in pairs]

    def remove_soft_deletion_dups(self, qnode_pairs):
        # Items that are soft-deleted in the old program will not be copied to
        # the new program. So filter out pairs where both items are effectively
        # deleted.
        return [(a, b) for (a, b) in qnode_pairs if a or b]

    def add_qnode_metadata(self, qnode_pairs, qnode_diff):
        # Create sets of ids; group by transform type
        deleted = {str(a.id) for a, b in qnode_pairs if b is None}
        added = {str(b.id) for a, b in qnode_pairs if a is None}
        relocated = {str(a.id) for a, b in qnode_pairs
                     if a and b and a.parent_id != b.parent_id}
        item_index = {str(a.id) for a, b in qnode_pairs
                      if a and b and a.seq != b.seq}

        reorder_ignore = set().union(deleted, added, relocated)

        reorder_time = 0.0
        for (a, b), diff_item in zip(qnode_pairs, qnode_diff):
            a_son, b_son = diff_item['pair']
            if a:
                a_son['path'] = a.get_path()
            if b:
                b_son['path'] = b.get_path()
            if a and b and str(a.parent_id) == str(b.parent_id):
                start = perf()
                if self.qnode_was_reordered(a, b, reorder_ignore):
                    diff_item['tags'].append('reordered')
                reorder_time += perf() - start
        self.timing.append("Qnode reorder filter took %gs" % reorder_time)

    def add_measure_metadata(self, measure_pairs, measure_diff):
        # Create sets of ids; group by transform type
        deleted = {str(a.id) for a, b in measure_pairs if b is None}
        added = {str(b.id) for a, b in measure_pairs if a is None}
        relocated = {str(a.id) for a, b in measure_pairs
                     if a and b and (a.get_qnode_measure(self.survey_id).qnode_id !=
                                     b.get_qnode_measure(self.survey_id).qnode_id)}
        item_index = {str(a.id) for a, b in measure_pairs
                      if a and b and (a.get_qnode_measure(self.survey_id).seq !=
                                      b.get_qnode_measure(self.survey_id).seq)}

        reorder_ignore = set().union(deleted, added, relocated)

        reorder_time = 0.0
        for (a, b), diff_item in zip(measure_pairs, measure_diff):
            a_son, b_son = diff_item['pair']
            if a:
                qm_a = a.get_qnode_measure(self.survey_id)
                a_son['path'] = qm_a.get_path()
                a_son['parentId'] = str(qm_a.qnode_id)
                a_son['surveyId'] = str(qm_a.survey_id)
                a_son['seq'] = qm_a.seq
            if b:
                qm_b = b.get_qnode_measure(self.survey_id)
                b_son['path'] = qm_b.get_path()
                b_son['parentId'] = str(qm_b.qnode_id)
                b_son['surveyId'] = str(qm_b.survey_id)
                b_son['seq'] = qm_b.seq
            if a and b and a_son['parentId'] == b_son['parentId']:
                start = perf()
                if self.measure_was_reordered(a, b, reorder_ignore):
                    diff_item['tags'].append('reordered')
                reorder_time += perf() - start
        self.timing.append("Measure reorder filter took %gs" % reorder_time)

    def qnode_was_reordered(self, a, b, reorder_ignore):
        a_siblings = (self.session.query(model.QuestionNode.id)
            .filter(model.QuestionNode.parent_id == a.parent_id,
                    model.QuestionNode.program_id == self.program_id_a,
                    ~model.QuestionNode.id.in_(reorder_ignore))
            .order_by(model.QuestionNode.seq)
            .all())
        b_siblings = (self.session.query(model.QuestionNode.id)
            .filter(model.QuestionNode.parent_id == b.parent_id,
                    model.QuestionNode.program_id == self.program_id_b,
                    ~model.QuestionNode.id.in_(reorder_ignore))
            .order_by(model.QuestionNode.seq)
            .all())
        a_siblings = [str(id_) for (id_,) in a_siblings]
        b_siblings = [str(id_) for (id_,) in b_siblings]
        if not str(a.id) in a_siblings or not str(b.id) in b_siblings:
            return False
        a_index = a_siblings.index(str(a.id))
        a_siblings = a_siblings[max(a_index - 1, 0):
                                min(a_index + 1, len(a_siblings))]
        b_index = b_siblings.index(str(b.id))
        b_siblings = b_siblings[max(b_index - 1, 0):
                                min(b_index + 1, len(b_siblings))]
        return a_siblings != b_siblings

    def measure_was_reordered(self, a, b, reorder_ignore):
        a_qnode_measure = a.get_qnode_measure(self.survey_id)
        b_qnode_measure = b.get_qnode_measure(self.survey_id)
        a_siblings = (self.session.query(model.Measure.id)
            .join(model.QnodeMeasure,
                  (model.QnodeMeasure.program_id == model.Measure.program_id) &
                  (model.QnodeMeasure.measure_id == model.Measure.id))
            .filter(model.QnodeMeasure.qnode_id == a_qnode_measure.qnode_id,
                    model.QnodeMeasure.program_id == self.program_id_a,
                    ~model.Measure.id.in_(reorder_ignore))
            .order_by(model.QnodeMeasure.seq)
            .all())
        b_siblings = (self.session.query(model.Measure.id)
            .join(model.QnodeMeasure,
                  (model.QnodeMeasure.program_id == model.Measure.program_id) &
                  (model.QnodeMeasure.measure_id == model.Measure.id))
            .filter(model.QnodeMeasure.qnode_id == b_qnode_measure.qnode_id,
                    model.QnodeMeasure.program_id == self.program_id_b,
                    ~model.Measure.id.in_(reorder_ignore))
            .order_by(model.QnodeMeasure.seq)
            .all())

        a_siblings = [str(id_) for (id_,) in a_siblings]
        b_siblings = [str(id_) for (id_,) in b_siblings]
        #log.error('Siblings A %s', a_siblings)
        #log.error('Siblings B %s', b_siblings)
        if not str(a.id) in a_siblings or not str(b.id) in b_siblings:
            return False
        a_index = a_siblings.index(str(a.id))
        a_siblings = a_siblings[max(a_index - 1, 0):
                                min(a_index + 1, len(a_siblings))]
        b_index = b_siblings.index(str(b.id))
        b_siblings = b_siblings[max(b_index - 1, 0):
                                min(b_index + 1, len(b_siblings))]
        return a_siblings != b_siblings

    def add_metadata(self, pairs, diff):
        for (a, b), diff_item in zip(pairs, diff):
            a_son, b_son = diff_item['pair']
            if a and b:
                if a_son['parentId'] != b_son['parentId']:
                    diff_item['tags'].append('relocated')
                elif a_son['seq'] != b_son['seq']:
                    diff_item['tags'].append('list index')
            elif a and not b:
                diff_item['tags'].append('deleted')
            elif b and not a:
                diff_item['tags'].append('added')

    def remove_unchanged_fields(self, diff, ignore=None, protect=None):
        if protect is None:
            protect = {'id', 'parentId', 'surveyId', 'title', 'path'}
        if ignore is None:
            ignore = {'id', 'parentId', 'surveyId', 'path', 'seq'}
        for diff_item in diff:
            a, b = diff_item['pair']
            keys = a is not None and a.keys() or b.keys()
            changes = 0
            for name in list(keys):
                changed = a and b and a[name] != b[name]
                if not changed and not name in protect:
                    if a:
                        del a[name]
                    if b:
                        del b[name]
                if changed and not name in ignore:
                    changes += 1
            if changes > 0:
                diff_item['tags'].append('modified')
