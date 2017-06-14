from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
import json
import os
import tempfile
import time
import uuid

import sqlalchemy
import sqlparse
from tornado import gen
from tornado.escape import json_encode, utf8, to_basestring
from tornado.concurrent import run_on_executor
import xlsxwriter

import config
import handlers
import model
import logging

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


class CustomQueryReportHandler(handlers.Paginate, handlers.BaseHandler):
    '''
    Allows ad-hoc queries using SQL.
    '''

    executor = ThreadPoolExecutor(max_workers=4)

    @handlers.authz('consultant')
    def get(self, file_type):
        to_son = ToSon(r'.*')
        self.set_header("Content-Type", "application/json")
        with model.session_scope() as session:
            conf = {
                'wall_time': config.get_setting(session, 'custom_timeout') * 1000,
                'max_limit': config.get_setting(session, 'custom_max_limit'),
            }
        self.write(json_encode(to_son(conf)))
        self.finish()

    @handlers.authz('consultant')
    @gen.coroutine
    def post(self, file_type):
        query = to_basestring(self.request.body)
        try:
            limit = float(self.get_argument('limit', '0'))
        except ValueError:
            raise handlers.ModelError(str(e))

        with model.session_scope() as session:
            max_limit = config.get_setting(session, 'custom_timeout') * 1000
            if limit == 0:
                limit = max_limit
            elif limit < 0:
                raise handlers.ModelError('Limit is too low')
            elif limit > max_limit:
                raise handlers.ModelError('Limit is too high')
            conf = {
                'wall_time': int(config.get_setting(session, 'custom_timeout') * 1000),
                'limit': int(limit),
            }

        if file_type == 'json':
            yield self.as_json(query, conf)
        elif file_type == 'csv':
            yield self.as_csv(query, conf)
        elif file_type == 'xlsx':
            yield self.as_xlsx(query, conf)
        else:
            raise handlers.MissingDocError('%s not supported' % file_type)

    def parse_cols(self, cursor):
        return [{
                'name': c.name,
                'type': TYPES.get(c.type_code, (None, None))[0],
                'rich_type': TYPES.get(c.type_code, (None, None))[1],
                'type_code': c.type_code
            } for c in cursor.description]

    def apply_config(self, session, conf):
        log.debug("Setting wall time to %d" % conf['wall_time'])
        try:
            session.execute("SET statement_timeout TO :wall_time",
                            {'wall_time': conf['wall_time']})
        except sqlalchemy.exc.SQLAlchemyError as e:
            raise handlers.ModelError(
                "Failed to prepare database session: %s" % e)

    @run_on_executor
    def export_json(self, path, query, conf):
        with model.session_scope(readonly=True) as session, \
                open(path, 'w', encoding='utf-8') as f:
            self.apply_config(session, conf)
            log.debug("Executing query for JSON export")

            try:
                result = session.execute(query)
            except sqlalchemy.exc.ProgrammingError as e:
                raise handlers.ModelError.from_sa(e, reason="")
            except sqlalchemy.exc.OperationalError as e:
                raise handlers.ModelError.from_sa(e, reason="")
            cols = self.parse_cols(result.context.cursor)

            to_son = ToSon(
                r'/[0-9]+$',
                r'/[0-9]+/[^/]+$',
            )
            f.write('{"cols": %s, "rows": [' % json_encode(to_son(cols)))

            first = True
            to_son = ToSon(
                r'/[0-9]+$',
            )
            chunksize = min(conf['limit'], CHUNKSIZE)
            n_read = 0
            while n_read < conf['limit']:
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
    def export_csv(self, path, query, conf):
        with model.session_scope(readonly=True) as session, \
                open(path, 'w', encoding='utf-8') as f:
            self.apply_config(session, conf)
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

            chunksize = min(conf['limit'], CHUNKSIZE)
            n_read = 0
            while n_read < conf['limit']:
                rows = result.fetchmany(chunksize)
                if len(rows) == 0:
                    break
                writer.writerows(rows)
                n_read += len(rows)
            self.reason('Read %d rows' % n_read)
            if result.fetchone():
                self.reason('Row limit reached; data truncated.')

    @run_on_executor
    def export_excel(self, path, query, conf):
        with model.session_scope(readonly=True) as session, \
                closing(xlsxwriter.Workbook(path)) as workbook:
            self.apply_config(session, conf)
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
            format_date = workbook.add_format({
                'valign': 'top', 'num_format': 'DD MMM YYYY'})

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
                elif col['rich_type'] == 'datetime':
                    worksheet_r.set_column(c, c, 40, format_date)
                else:
                    worksheet_r.set_column(c, c, 20)
            worksheet_r.set_row(0, None, format_bold)
            for c, col in enumerate(cols):
                worksheet_r.write(0, c, col['name'])

            chunksize = min(conf['limit'], CHUNKSIZE)
            n_read = 0
            while n_read < conf['limit']:
                rows = result.fetchmany(chunksize)
                if len(rows) == 0:
                    break
                for r, row in enumerate(rows):
                    for c, (cell, col) in enumerate(zip(row, cols)):
                        if col['type'] == 'string':
                            data = str(cell)
                        else:
                            data = cell
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
    def as_json(self, query, conf):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, 'query_result.json')
            yield self.export_json(path, query, conf)

            self.set_header("Content-Type", "application/json")
            self.set_header(
                'Content-Disposition', 'attachment')
            self.transfer_file(path)
        self.finish()

    @gen.coroutine
    def as_csv(self, query, conf):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, 'query_result.csv')
            yield self.export_csv(path, query, conf)

            self.set_header("Content-Type", "text/csv")
            self.set_header(
                'Content-Disposition', 'attachment')
            self.transfer_file(path)
        self.finish()

    @gen.coroutine
    def as_xlsx(self, query, conf):
        with tempfile.TemporaryDirectory() as tempdir:
            path = os.path.join(tempdir, 'query_result.xlsx')
            yield self.export_excel(path, query, conf)

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
                data = f.read(BUF_SIZE)
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


class SqlIdentifierHandler(handlers.BaseHandler):
    @handlers.authz('consultant')
    def post(self):
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
