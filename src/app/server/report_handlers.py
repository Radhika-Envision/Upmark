from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
import json
import os
import tempfile
import time
import uuid

import sqlalchemy
from sqlalchemy import String
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import cast, literal
import sqlparse
from tornado import gen
from tornado.escape import json_decode, json_encode, utf8, to_basestring
from tornado import gen
import tornado.web
from tornado.concurrent import run_on_executor
import xlsxwriter

import handlers
import model
import logging

from utils import falsy, ToSon, truthy


MAX_WORKERS = 4

log = logging.getLogger('app.report_handlers')


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


class DiffHandler(handlers.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def get(self):
        survey_id_a = self.get_argument("surveyId1", '')
        survey_id_b = self.get_argument("surveyId2", '')
        hierarchy_id = self.get_argument("hierarchyId", '')

        ignore_tags = set().union(self.get_arguments("ignoreTag"))

        if survey_id_a == '':
            raise handlers.ModelError("Survey ID 1 required")
        if survey_id_b == '':
            raise handlers.ModelError("Survey ID 2 required")
        if hierarchy_id == '':
            raise handlers.ModelError("Hierarchy ID required")

        include_scores = self.current_user.role != 'clerk'

        son, details = yield self.background_task(
            survey_id_a, survey_id_b, hierarchy_id, ignore_tags, include_scores)

        for i, message in enumerate(details):
            self.add_header('Profiling', "%d %s" % (i, message))

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @run_on_executor
    def background_task(
            self, survey_id_a, survey_id_b, hierarchy_id, ignore_tags,
            include_scores):

        with model.session_scope() as session:
            self.check_browse_survey(session, survey_id_a, hierarchy_id)
            self.check_browse_survey(session, survey_id_b, hierarchy_id)

            diff_engine = DiffEngine(
                session, survey_id_a, survey_id_b, hierarchy_id, include_scores)
            diff = diff_engine.execute()
            diff = [di for di in diff
                    if len(set().union(di['tags']).difference(ignore_tags)) > 0]
            son = {
                'diff': diff
            }
        return son, diff_engine.timing


class DiffEngine:
    def __init__(self, session, survey_id_a, survey_id_b, hierarchy_id,
                 include_scores=True):
        self.session = session
        self.survey_id_a = survey_id_a
        self.survey_id_b = survey_id_b
        self.hierarchy_id = hierarchy_id
        self.include_scores = include_scores
        self.timing = []

    def execute(self):
        qnode_pairs = self.get_qnodes()
        measure_pairs = self.get_measures()

        include=[
            r'/id$',
            r'/parent_id$',
            r'/title$',
            r'/description$',
            r'/intent$',
            r'/inputs$',
            r'/scenario$',
            r'/questions$',
            r'/response_type$',
            r'/seq$',
            # Descend
            r'/[0-9]+$',
            r'^/[0-9]+/[^/]+$',
        ]

        if self.include_scores:
            include += [
                r'/weight$',
            ]
        to_son = ToSon(include=include)

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

        HA = model.Hierarchy
        HB = aliased(model.Hierarchy, name='hierarchy_b')
        hierarchy_a, hierarchy_b = (self.session.query(HA, HB)
            .join(HB, (HA.id == HB.id))
            .filter(HA.survey_id == self.survey_id_a,
                    HB.survey_id == self.survey_id_b,
                    HA.id == self.hierarchy_id)
            .first())
        to_son = ToSon(include=[
            r'/id$',
            r'/title$',
            r'/description$'
        ])
        top_level_diff = [
            {
                'type': 'survey',
                'tags': ['context'],
                'pair': [to_son(hierarchy_a.survey), to_son(hierarchy_b.survey)]
            },
            {
                'type': 'hierarchy',
                'tags': ['context'],
                'pair': [to_son(hierarchy_a), to_son(hierarchy_b)]
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
            .filter(QA.survey_id == self.survey_id_a,
                    QB.survey_id == self.survey_id_b,
                    QA.hierarchy_id == self.hierarchy_id,
                    QB.hierarchy_id == self.hierarchy_id)

            # Filter for modified objects
            .filter((QA.title != QB.title) |
                    (QA.description != QB.description) |
                    (QA.parent_id != QB.parent_id) |
                    (QA.seq != QB.seq))
        )

        # Find deleted qnodes
        qnode_del_query = (self.session.query(QA, literal(None))
            .select_from(QA)
            .filter(QA.survey_id == self.survey_id_a,
                    QA.hierarchy_id == self.hierarchy_id,
                    ~QA.id.in_(
                        self.session.query(QB.id)
                            .filter(QB.survey_id == self.survey_id_b,
                                    QB.hierarchy_id == self.hierarchy_id,
                                    QB.deleted == False)))
        )

        # Find added qnodes
        qnode_add_query = (self.session.query(literal(None), QB)
            .select_from(QB)
            .filter(QB.survey_id == self.survey_id_b,
                    QB.hierarchy_id == self.hierarchy_id,
                    ~QB.id.in_(
                        self.session.query(QA.id)
                            .filter(QA.survey_id == self.survey_id_a,
                                    QA.hierarchy_id == self.hierarchy_id,
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
        QMB = aliased(model.QnodeMeasure, name='qnode_measure_link_b')

        start = perf()

        # Find modified / relocated measures
        measure_mod_query = (self.session.query(MA, MB)

            .join(MB, MA.id == MB.id)

            .join(QMA,
                  (QMA.survey_id == MA.survey_id) &
                  (QMA.measure_id == MA.id))
            .join(QMB,
                  (QMB.survey_id == MB.survey_id) &
                  (QMB.measure_id == MB.id))
            .join(QA,
                  (QMA.survey_id == QA.survey_id) &
                  (QMA.qnode_id == QA.id))
            .join(QB,
                  (QMB.survey_id == QB.survey_id) &
                  (QMB.qnode_id == QB.id))

            # Basic survey membership
            .filter(QA.survey_id == self.survey_id_a,
                    QB.survey_id == self.survey_id_b,
                    QA.hierarchy_id == self.hierarchy_id,
                    QB.hierarchy_id == self.hierarchy_id)

            # Filter for modified objects
            .filter((MA.title != MB.title) |
                    (MA.intent != MB.intent) |
                    (MA.inputs != MB.inputs) |
                    (MA.scenario != MB.scenario) |
                    (MA.questions != MB.questions) |
                    (MA.response_type != MB.response_type) |
                    (MA.weight != MB.weight) |
                    (QMA.qnode_id != QMB.qnode_id) |
                    (QMA.seq != QMB.seq))
        )

        # Find deleted measures
        measure_del_query = (self.session.query(MA, literal(None))
            .select_from(MA)
            .join(QMA,
                  (QMA.survey_id == MA.survey_id) &
                  (QMA.measure_id == MA.id))
            .join(QA,
                  (QMA.survey_id == QA.survey_id) &
                  (QMA.qnode_id == QA.id))
            .filter(QA.survey_id == self.survey_id_a,
                    QA.hierarchy_id == self.hierarchy_id,
                    ~QMA.measure_id.in_(
                        self.session.query(QMB.measure_id)
                            .join(QB,
                                  (QMB.survey_id == QB.survey_id) &
                                  (QMB.qnode_id == QB.id))
                            .filter(QB.survey_id == self.survey_id_b,
                                    QB.hierarchy_id == self.hierarchy_id)))
        )

        # Find added measures
        measure_add_query = (self.session.query(literal(None), MB)
            .select_from(MB)
            .join(QMB,
                  (QMB.survey_id == MB.survey_id) &
                  (QMB.measure_id == MB.id))
            .join(QB,
                  (QMB.survey_id == QB.survey_id) &
                  (QMB.qnode_id == QB.id))
            .filter(QB.survey_id == self.survey_id_b,
                    QB.hierarchy_id == self.hierarchy_id,
                    ~QMB.measure_id.in_(
                        self.session.query(QMA.measure_id)
                            .join(QA,
                                  (QMA.survey_id == QA.survey_id) &
                                  (QMA.qnode_id == QA.id))
                            .filter(QA.survey_id == self.survey_id_a,
                                    QA.hierarchy_id == self.hierarchy_id)))
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

            if hasattr(x, 'get_parent'):
                # measure
                if x.deleted:
                    return None
                q = x.get_parent(self.hierarchy_id)
            else:
                # qnode
                q = x

            if q.any_deleted():
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
                     if a and b and (a.get_parent(self.hierarchy_id).id !=
                                     b.get_parent(self.hierarchy_id).id)}
        item_index = {str(a.id) for a, b in measure_pairs
                      if a and b and (a.get_seq(self.hierarchy_id) !=
                                      b.get_seq(self.hierarchy_id))}

        reorder_ignore = set().union(deleted, added, relocated)

        reorder_time = 0.0
        for (a, b), diff_item in zip(measure_pairs, measure_diff):
            a_son, b_son = diff_item['pair']
            if a:
                a_son['path'] = a.get_path(self.hierarchy_id)
                a_son['parentId'] = str(a.get_parent(self.hierarchy_id).id)
                a_son['seq'] = a.get_seq(self.hierarchy_id)
            if b:
                b_son['path'] = b.get_path(self.hierarchy_id)
                b_son['parentId'] = str(b.get_parent(self.hierarchy_id).id)
                b_son['seq'] = b.get_seq(self.hierarchy_id)
            if a and b and a_son['parentId'] == b_son['parentId']:
                start = perf()
                if self.measure_was_reordered(a, b, reorder_ignore):
                    diff_item['tags'].append('reordered')
                reorder_time += perf() - start
        self.timing.append("Measure reorder filter took %gs" % reorder_time)

    def qnode_was_reordered(self, a, b, reorder_ignore):
        a_siblings = (self.session.query(model.QuestionNode.id)
            .filter(model.QuestionNode.parent_id == a.parent_id,
                    model.QuestionNode.survey_id == self.survey_id_a,
                    ~model.QuestionNode.id.in_(reorder_ignore))
            .order_by(model.QuestionNode.seq)
            .all())
        b_siblings = (self.session.query(model.QuestionNode.id)
            .filter(model.QuestionNode.parent_id == b.parent_id,
                    model.QuestionNode.survey_id == self.survey_id_b,
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
        a_parent = a.get_parent(self.hierarchy_id)
        b_parent = b.get_parent(self.hierarchy_id)
        a_siblings = (self.session.query(model.Measure.id)
            .join(model.QnodeMeasure,
                  (model.QnodeMeasure.survey_id == model.Measure.survey_id) &
                  (model.QnodeMeasure.measure_id == model.Measure.id))
            .filter(model.QnodeMeasure.qnode_id == a_parent.id,
                    model.QnodeMeasure.survey_id == self.survey_id_a,
                    ~model.Measure.id.in_(reorder_ignore))
            .order_by(model.QnodeMeasure.seq)
            .all())
        b_siblings = (self.session.query(model.Measure.id)
            .join(model.QnodeMeasure,
                  (model.QnodeMeasure.survey_id == model.Measure.survey_id) &
                  (model.QnodeMeasure.measure_id == model.Measure.id))
            .filter(model.QnodeMeasure.qnode_id == b_parent.id,
                    model.QnodeMeasure.survey_id == self.survey_id_b,
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
            protect = {'id', 'parentId', 'title', 'path'}
        if ignore is None:
            ignore = {'id', 'parentId', 'path', 'seq'}
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


class AdHocHandler(handlers.Paginate, handlers.BaseHandler):
    '''
    Allows ad-hoc queries using SQL.
    '''

    executor = ThreadPoolExecutor(max_workers=4)

    TYPES = {
        2950:   ('string',  'uuid'),
        25:     ('string',  'text'),
        1043:   ('string',  'enum'),
        1114:   ('date',    'datetime'),
        23:     ('int',     'int'),
        701:    ('float',   'float'),
        16:     ('bool',    'bool'),
        114:    ('string',  'json')
    }
    CHUNKSIZE = 100
    MAX_LIMIT = 2500
    BUF_SIZE = 4096

    @handlers.authz('consultant')
    def get(self, file_type):
        to_son = ToSon(include=[r'.*'])
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(to_son(self.config)))
        self.finish()

    @handlers.authz('consultant')
    @gen.coroutine
    def post(self, file_type):
        query = to_basestring(self.request.body)
        limit = int(self.get_argument('limit', self.config['max_limit']))
        if limit > self.config['max_limit']:
            raise handlers.ModelError(
                'Limit is too high. Max %d' % self.config['max_limit'])

        if file_type == 'json':
            yield self.as_json(query, limit)
        elif file_type == 'csv':
            yield self.as_csv(query, limit)
        elif file_type == 'xlsx':
            yield self.as_xlsx(query, limit)
        else:
            raise handlers.MissingDocError('%s not supported' % file_type)

    @property
    def config(self):
        log.debug("Reading config")
        if hasattr(self, '_config'):
            return self._config

        _config = {}
        with model.session_scope() as session:
            try:
                wall_time = (session.query(model.SystemConfig)
                    .get('adhoc_timeout'))
                if wall_time is None:
                    raise ValueError("adhoc_timeout is not defined")
                _config['wall_time'] = int(float(wall_time.value) * 1000)
                if _config['wall_time'] < 0:
                    raise ValueError("adhoc_timeout must be non-negative")
            except (ValueError, sqlalchemy.exc.SQLAlchemyError) as e:
                raise handlers.ModelError(
                    "Failed to get settings: %s" % e)

            try:
                max_limit = (session.query(model.SystemConfig)
                    .get('adhoc_max_limit'))
                if max_limit is None:
                    raise ValueError("adhoc_max_limit is not defined")
                _config['max_limit'] = int(max_limit.value)
                if _config['max_limit'] < 0:
                    raise ValueError("adhoc_max_limit must be positive")
            except (ValueError, sqlalchemy.exc.SQLAlchemyError) as e:
                raise handlers.ModelError(
                    "Failed to get settings: %s" % e)

        self._config = _config
        return self._config

    def parse_cols(self, cursor):
        return [{
                'name': c.name,
                'type': AdHocHandler.TYPES.get(c.type_code, (None, None))[0],
                'rich_type': AdHocHandler.TYPES.get(c.type_code, (None, None))[1],
                'type_code': c.type_code
            } for c in cursor.description]

    def apply_config(self, session):
        log.debug("Setting wall time to %d" % self._config['wall_time'])
        try:
            session.execute("SET statement_timeout TO :wall_time",
                            {'wall_time': self._config['wall_time']})
        except sqlalchemy.exc.SQLAlchemyError as e:
            raise handlers.ModelError(
                "Failed to prepare database session: %s" % e)

    @run_on_executor
    def export_json(self, path, query, limit):
        with model.session_scope(readonly=True) as session, \
                open(path, 'w', encoding='utf-8') as f:
            self.apply_config(session)
            log.debug("Executing query for JSON export")

            try:
                result = session.execute(query)
            except sqlalchemy.exc.ProgrammingError as e:
                raise handlers.ModelError.from_sa(e, reason="")
            except sqlalchemy.exc.OperationalError as e:
                raise handlers.ModelError.from_sa(e, reason="")
            cols = self.parse_cols(result.context.cursor)

            to_son = ToSon(include=[
                r'/[0-9]+$',
                r'/[0-9]+/[^/]+$'
            ])
            f.write('{"cols": %s, "rows": [' % json_encode(to_son(cols)))

            first = True
            to_son = ToSon(include=[
                r'/[0-9]+$'
            ])
            chunksize = min(limit, AdHocHandler.CHUNKSIZE)
            n_read = 0
            while n_read < limit:
                rows = result.fetchmany(chunksize)
                if len(rows) == 0:
                    break
                for row in rows:
                    if not first:
                        f.write(', ')
                    f.write(json_encode(to_son(row)))
                    first = False
                n_read += len(rows)
            f.write(']}')
            self.reason('Read %d rows' % n_read)
            if result.fetchone():
                self.reason('Row limit reached; data truncated.')

    @run_on_executor
    def export_csv(self, path, query, limit):
        with model.session_scope(readonly=True) as session, \
                open(path, 'w', encoding='utf-8') as f:
            self.apply_config(session)
            log.debug("Executing query for CSV export")

            writer = csv.writer(f)
            try:
                result = session.execute(query)
            except sqlalchemy.exc.ProgrammingError as e:
                raise handlers.ModelError.from_sa(e, reason="")
            except sqlalchemy.exc.OperationalError as e:
                raise handlers.ModelError.from_sa(e, reason="")
            cols = self.parse_cols(result.context.cursor)
            writer.writerow([c['name'] for c in cols])

            chunksize = min(limit, AdHocHandler.CHUNKSIZE)
            n_read = 0
            while n_read < limit:
                rows = result.fetchmany(chunksize)
                if len(rows) == 0:
                    break
                writer.writerows(rows)
                n_read += len(rows)
            self.reason('Read %d rows' % n_read)
            if result.fetchone():
                self.reason('Row limit reached; data truncated.')

    @run_on_executor
    def export_excel(self, path, query, limit):
        with model.session_scope(readonly=True) as session, \
                closing(xlsxwriter.Workbook(path)) as workbook:
            self.apply_config(session)
            log.debug("Executing query for Excel export")

            try:
                result = session.execute(query)
            except sqlalchemy.exc.ProgrammingError as e:
                raise handlers.ModelError.from_sa(e, reason="")
            except sqlalchemy.exc.OperationalError as e:
                raise handlers.ModelError.from_sa(e, reason="")

            format_str = workbook.add_format({
                'valign': 'top'})
            format_str_wrap = workbook.add_format({
                'valign': 'top', 'text_wrap': True})
            format_float = workbook.add_format({
                'valign': 'top', 'num_format': '#,##0.00'})
            format_int = workbook.add_format({
                'valign': 'top', 'num_format': '#,##0'})

            format_bold = workbook.add_format({'bold': True})

            worksheet_q = workbook.add_worksheet('query')
            worksheet_q.set_column(0, 0, 80, format_str_wrap)
            worksheet_q.write(0, 0, query)

            worksheet_r = workbook.add_worksheet('result')
            cols = self.parse_cols(result.context.cursor)
            for c, col in enumerate(cols):
                if col['type'] == 'int':
                    worksheet_r.set_column(c, c, 10, format_int)
                elif col['type'] == 'float':
                    worksheet_r.set_column(c, c, 10, format_float)
                elif col['rich_type'] == 'uuid':
                    worksheet_r.set_column(c, c, 10, format_str)
                elif col['rich_type'] == 'text':
                    worksheet_r.set_column(c, c, 40, format_str_wrap)
                else:
                    worksheet_r.set_column(c, c, 20)
            worksheet_r.set_row(0, None, format_bold)
            for c, col in enumerate(cols):
                worksheet_r.write(0, c, col['name'])

            chunksize = min(limit, AdHocHandler.CHUNKSIZE)
            n_read = 0
            while n_read < limit:
                rows = result.fetchmany(chunksize)
                if len(rows) == 0:
                    break
                for r, row in enumerate(rows):
                    for c, (cell, col) in enumerate(zip(row, cols)):
                        data = cell
                        if col['type'] == 'string':
                            data = str(cell)
                        worksheet_r.write(r + n_read + 1, c, data)
                n_read += len(rows)
            self.reason('Read %d rows' % n_read)
            if result.fetchone():
                self.reason('Row limit reached; data truncated.')
                worksheet_r.insert_textbox(
                    1, 1, 'Row limit reached; data truncated.',
                    {'width': 400, 'height': 200,
                     'x_offset': 10, 'y_offset': 10,
                     'fill': {'color': "#ffdd88"},
                     'border': {'color': "#634E19"},
                     'font': {'color': "#634E19"},
                     'align': {
                        'vertical': 'middle',
                        'horizontal': 'center'
                     }})

            worksheet_r.activate()

    @gen.coroutine
    def as_json(self, query, limit):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, 'query_result.json')
            yield self.export_json(path, query, limit)

            self.set_header("Content-Type", "application/json")
            self.set_header(
                'Content-Disposition', 'attachment; filename=query_result.json')
            self.transfer_file(path)
        self.finish()

    @gen.coroutine
    def as_csv(self, query, limit):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, 'query_result.csv')
            yield self.export_csv(path, query, limit)

            self.set_header("Content-Type", "text/csv")
            self.set_header(
                'Content-Disposition', 'attachment; filename=query_result.csv')
            self.transfer_file(path)
        self.finish()

    @gen.coroutine
    def as_xlsx(self, query, limit):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, 'query_result.xlsx')
            yield self.export_excel(path, query, limit)

            self.set_header("Content-Type",
                            "application/vnd.openxmlformats-officedocument"
                            ".spreadsheetml.sheet")
            self.set_header(
                'Content-Disposition',
                'attachment; filename=query_result.xlsx')
            self.transfer_file(path)
        self.finish()

    def transfer_file(self, path):
        with open(path, 'rb') as f:
            while True:
                data = f.read(AdHocHandler.BUF_SIZE)
                if not data:
                    break
                self.write(data)


class SqlFormatHandler(handlers.BaseHandler):
    @handlers.authz('consultant')
    def post(self):
        query = to_basestring(self.request.body)
        query = sqlparse.format(
            query, keyword_case='upper', identifier_case='lower',
            reindent=True, indent_width=4)

        self.set_header("Content-Type", "text/plain")
        self.write(utf8(query))
        self.finish()
