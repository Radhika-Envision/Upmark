from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
from datetime import datetime
import logging
import os
import tempfile

from munch import DefaultMunch
import sqlalchemy
import sqlparse
import tornado
from tornado import gen
from tornado.escape import json_encode, utf8, to_basestring
from tornado.concurrent import run_on_executor
import xlsxwriter

import base_handler
import config
import errors
import model
from undefined import undefined
from utils import ToSon


log = logging.getLogger('app.report.custom')


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


class CustomQueryReportHandler(base_handler.BaseHandler):
    '''
    Runs custom stored SQL queries.
    '''

    @tornado.web.authenticated
    @gen.coroutine
    def post(self, query_id, file_type):
        with model.session_scope() as session:
            custom_query = session.query(model.CustomQuery).get(query_id)
            if not custom_query:
                raise errors.MissingDocError("No such query")

            user_session = self.get_user_session(session)
            policy = user_session.policy.derive({
                'custom_query': custom_query,
            })
            policy.verify('custom_query_execute')

            if not custom_query.text:
                raise errors.ModelError("Query is empty")

            conf = self.get_config(session)
            session.expunge(custom_query)

        yield self.export(custom_query, conf, file_type)
        self.finish()

    def get_config(self, session):
        try:
            limit = float(self.get_argument('limit', '0'))
            wall_time = float(self.get_argument('wall_time', '0'))
        except ValueError as e:
            raise errors.ModelError(str(e))

        max_wall_time = config.get_setting(session, 'custom_timeout') * 1000
        if wall_time == 0:
            wall_time = max_wall_time
        elif not 0 <= wall_time <= max_wall_time:
            raise errors.ModelError('Query wall time is out of bounds')

        max_limit = config.get_setting(session, 'custom_max_limit')
        if limit == 0:
            limit = max_limit
        elif not 0 <= limit <= max_limit:
            raise errors.ModelError('Query row limit is out of bounds')

        return DefaultMunch(
            undefined,
            {
                'wall_time': int(wall_time * 1000),
                'limit': int(limit),
                'base_url': config.get_setting(session, 'app_base_url'),
            }
        )

    @gen.coroutine
    def export(self, custom_query, conf, file_type):
        if file_type == 'json':
            writer = JsonWriter()
        elif file_type == 'csv':
            writer = CsvWriter()
        elif file_type == 'xlsx':
            writer = ExcelWriter(conf.base_url)
        else:
            raise errors.MissingDocError('%s not supported' % file_type)

        runner = QueryRunner(writer)
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, 'query_result')
            messages = yield runner.export(path, custom_query, conf)
            for message in messages:
                self.reason(message)
            self.set_header("Content-Type", writer.content_type)
            self.set_header('Content-Disposition', 'attachment')
            self.transfer_file(path)

    def transfer_file(self, path):
        with open(path, 'rb') as f:
            while True:
                data = f.read(BUF_SIZE)
                if not data:
                    break
                self.write(data)


class CustomQueryPreviewHandler(CustomQueryReportHandler):
    '''
    Allows ad-hoc queries using SQL.
    '''

    @tornado.web.authenticated
    @gen.coroutine
    def post(self, file_type):
        with model.session_scope() as session:
            user_session = self.get_user_session(session)
            policy = user_session.policy.derive({})
            policy.verify('custom_query_preview')

            text = to_basestring(self.request.body)
            if not text:
                raise errors.ModelError("Query is empty")
            custom_query = model.CustomQuery(description="Preview", text=text)

            conf = self.get_config(session)

        yield self.export(custom_query, conf, file_type)
        self.finish()


class QueryRunner:

    executor = ThreadPoolExecutor(max_workers=4)

    def __init__(self, writer):
        self.writer = writer

    @run_on_executor
    def export(self, path, query, conf):
        with model.session_scope(readonly=True) as session:
            self.apply_config(session, conf)
            result = self.execute(session, query.text)
            resultset = ResultSet(result, conf.limit)
            self.writer.write(session, resultset, path, query)

            return [m for m in resultset.messages]

    def apply_config(self, session, conf):
        log.debug("Setting wall time to %d" % conf.wall_time)
        try:
            session.execute("SET statement_timeout TO :wall_time",
                            {'wall_time': conf.wall_time})
        except sqlalchemy.exc.SQLAlchemyError as e:
            raise errors.ModelError(
                "Failed to prepare database session: %s" % e)

    def execute(self, session, text):
        try:
            return session.execute(text)
        except sqlalchemy.exc.ProgrammingError as e:
            raise errors.ModelError.from_sa(e, reason="")
        except sqlalchemy.exc.OperationalError as e:
            raise errors.ModelError.from_sa(e, reason="")


class ResultSet:
    def __init__(self, result, limit):
        self.result = result
        self.limit = limit
        self.n_read = 0
        self.is_exhausted = False

    @property
    def cols(self):
        return [{
            'name': c.name,
            'type': TYPES.get(c.type_code, (None, None))[0],
            'rich_type': TYPES.get(c.type_code, (None, None))[1],
            'type_code': c.type_code
        } for c in self.result.context.cursor.description]

    @property
    def rows(self):
        chunksize = min(self.limit, CHUNKSIZE)
        while self.n_read < self.limit:
            rows = self.result.fetchmany(chunksize)
            if len(rows) == 0:
                break
            for row in rows:
                yield row
                self.n_read += 1
        if self.result.fetchone():
            self.is_exhausted = True

    @property
    def messages(self):
        yield 'Read %d rows' % self.n_read
        if self.is_exhausted:
            yield 'Row limit reached; data truncated.'


class JsonWriter:
    content_type = 'application/json'

    def write(self, session, resultset, path, query):
        with open(path, 'w', encoding='utf-8') as f:
            log.debug("Writing result as JSON")

            to_son = ToSon(
                r'/[0-9]+$',
                r'/[0-9]+/[^/]+$',
            )
            f.write('{"cols": %s, "rows": [' % json_encode(
                to_son(resultset.cols)))

            to_son = ToSon(
                r'/[0-9]+$',
            )
            for i, row in enumerate(resultset.rows):
                if i > 0:
                    f.write(', ')
                f.write(json_encode(to_son(row)))
            f.write(']}')


class CsvWriter:
    content_type = 'text/csv'

    def write(self, session, resultset, path, query):
        with open(path, 'w', encoding='utf-8') as f:
            log.debug("Writing result as CSV")

            writer = csv.writer(f)
            writer.writerow([c['name'] for c in resultset.cols])

            for row in resultset.rows:
                writer.writerow(row)


class ExcelWriter:
    content_type = 'application/' \
                   'vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    def __init__(self, base_url):
        self.base_url = base_url

    def write(self, session, resultset, path, query):
        with closing(xlsxwriter.Workbook(path)) as workbook:
            log.debug("Writing result as Excel")

            format_str = workbook.add_format({
                'valign': 'top'})
            format_str_wrap = workbook.add_format({
                'valign': 'top', 'text_wrap': True})
            format_float = workbook.add_format({
                'valign': 'top', 'num_format': '#,##0.00'})
            format_int = workbook.add_format({
                'valign': 'top', 'num_format': '#,##0'})
            format_date = workbook.add_format({
                'valign': 'top', 'num_format': 'DD MMM YYYY'})

            format_bold = workbook.add_format({'bold': True})

            worksheet_q = workbook.add_worksheet('query')
            worksheet_q.set_column(0, 1, 80, format_str_wrap)
            worksheet_q.write(0, 0, "Title")
            worksheet_q.write(0, 1, query.title)
            worksheet_q.write(1, 0, "Description")
            worksheet_q.write(1, 1, query.description)
            worksheet_q.write(2, 0, "Date")
            worksheet_q.write(2, 1, datetime.now(), format_date)
            worksheet_q.write(3, 0, "URL")
            worksheet_q.write_url(3, 1, "%s/#/3/custom/%s" % (
                self.base_url, query.id))

            worksheet_r = workbook.add_worksheet('result')
            cols = resultset.cols
            for c, col in enumerate(cols):
                if col['type'] == 'int':
                    worksheet_r.set_column(c, c, 10, format_int)
                elif col['type'] == 'float':
                    worksheet_r.set_column(c, c, 10, format_float)
                elif col['rich_type'] == 'uuid':
                    worksheet_r.set_column(c, c, 10, format_str)
                elif col['rich_type'] == 'text':
                    worksheet_r.set_column(c, c, 40, format_str_wrap)
                elif col['rich_type'] == 'datetime':
                    worksheet_r.set_column(c, c, 40, format_date)
                else:
                    worksheet_r.set_column(c, c, 20)
            worksheet_r.set_row(0, None, format_bold)
            for c, col in enumerate(cols):
                worksheet_r.write(0, c, col['name'])

            for r, row in enumerate(resultset.rows, start=1):
                for c, (cell, col) in enumerate(zip(row, cols)):
                    if col['type'] == 'string':
                        data = str(cell)
                    else:
                        data = cell
                    worksheet_r.write(r, c, data)

            if resultset.is_exhausted:
                worksheet_r.insert_textbox(
                    1, 1, 'Row limit reached; data truncated.',
                    {
                        'width': 400, 'height': 200,
                        'x_offset': 10, 'y_offset': 10,
                        'fill': {'color': "#ffdd88"},
                        'border': {'color': "#634E19"},
                        'font': {'color': "#634E19"},
                        'align': {
                            'vertical': 'middle',
                            'horizontal': 'center',
                        },
                    })

            worksheet_r.activate()


class CustomQueryConfigHandler(base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self):
        with model.session_scope() as session:
            user_session = self.get_user_session(session)
            policy = user_session.policy.derive({})
            policy.verify('custom_query_view')

            to_son = ToSon(r'.*')
            self.set_header("Content-Type", "application/json")

            wall_time = config.get_setting(session, 'custom_timeout') * 1000
            max_limit = config.get_setting(session, 'custom_max_limit')
            conf = {'wall_time': wall_time, 'max_limit': max_limit}

        self.write(json_encode(to_son(conf)))
        self.finish()


class SqlFormatHandler(base_handler.BaseHandler):

    @tornado.web.authenticated
    def post(self):
        with model.session_scope() as session:
            user_session = self.get_user_session(session)
            policy = user_session.policy.derive({})
            policy.verify('custom_query_add')

        query = to_basestring(self.request.body)
        query = sqlparse.format(
            query, keyword_case='upper', identifier_case='lower',
            reindent=True, indent_width=4)

        self.set_header("Content-Type", "text/plain")
        self.write(utf8(query))
        self.finish()


class SqlIdentifierHandler(base_handler.BaseHandler):

    @tornado.web.authenticated
    def post(self):
        with model.session_scope() as session:
            user_session = self.get_user_session(session)
            policy = user_session.policy.derive({})
            policy.verify('custom_query_add')

        query = to_basestring(self.request.body)

        extractor = NameExtractor()
        extractor.handle_query(query)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode({
            'autoName': extractor.auto_name,
            'namesByKw': {
                k: sorted(vs)
                for k, vs in extractor.names_by_kw.items()},
        }))
        self.finish()


class NameExtractor:
    def __init__(self):
        self.names_by_kw = defaultdict(set)
        self.auto_name = ""
        self.keyword = None

    def handle_query(self, query):
        for statement in sqlparse.parse(query):
            self.handle_statement(statement)

        self.auto_name = ' '.join(self.names_by_kw['from'])
        if self.names_by_kw['join']:
            self.auto_name += ' by ' + ' '.join(self.names_by_kw['join'])

    def handle_statement(self, statement):
        for token in statement.tokens:
            if token.is_keyword:
                self.handle_keyword(token)
            elif isinstance(token, sqlparse.sql.IdentifierList):
                self.handle_identifier_list(token)
            elif isinstance(token, sqlparse.sql.Identifier):
                self.handle_identifier(token)

    def handle_keyword(self, keyword):
        self.keyword = keyword.value.lower()

    def handle_identifier_list(self, identifier_list):
        for token in identifier_list.tokens:
            if isinstance(token, sqlparse.sql.Identifier):
                self.handle_identifier(token)

    def handle_identifier(self, identifier):
        self.names_by_kw[self.keyword].add(identifier.get_real_name())
