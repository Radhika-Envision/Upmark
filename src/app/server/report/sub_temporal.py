from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import datetime
import itertools
import logging
from numbers import Number
import os
import tempfile

import numpy as np
from sqlalchemy import true, false
from sqlalchemy.orm import joinedload
from tornado import gen
from tornado.concurrent import run_on_executor
import tornado.web
import xlsxwriter

import base_handler
from crud.approval import APPROVAL_STATES
import errors
import model
from utils import keydefaultdict


BUF_SIZE = 4096
MAX_WORKERS = 4
MIN_CONSITUENTS = 5

log = logging.getLogger('app.report.temporal')


class TemporalReportHandler(base_handler.BaseHandler):
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    @tornado.web.authenticated
    @gen.coroutine
    def post(self, survey_id, extension):

        parameters = self.get_parameters()
        organisation_id = parameters.organisation_id

        try:
            parameters['min_constituents'] = int(
                parameters.get('min_constituents', MIN_CONSITUENTS))
        except ValueError:
            raise errors.ModelError("Invalid minimum number of constituents")

        if 'approval' not in parameters:
            raise errors.ModelError("Approval status required")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)
            if organisation_id:
                org = session.query(model.Organisation).get(organisation_id)
            else:
                org = None

            if org:
                policy = user_session.policy.derive({
                    'surveygroups': org.surveygroups,
                })
                policy.verify('surveygroup_interact')

            policy = user_session.policy.derive({
                'org': org,
                'consituents': parameters['min_constituents'],
                'approval': parameters['approval'],
            })
            policy.verify('report_temporal')

            if not policy.check('surveygroup_interact_all'):
                surveygroup_ids = [
                    surveygroup.id
                    for surveygroup in user_session.user.surveygroups]
            else:
                surveygroup_ids = None

        with tempfile.TemporaryDirectory() as tmpdir:
            outpath, outfile, info = yield self.process_temporal(
                parameters, survey_id, tmpdir, extension, surveygroup_ids)

            for message in info:
                self.reason(message)

            self.set_header('Content-Type', 'application/octet-stream')
            self.set_header(
                'Content-Disposition', 'attachment')

            with open(outpath, 'rb') as f:
                while True:
                    data = f.read(BUF_SIZE)
                    if not data:
                        break
                    self.write(data)

        self.finish()

    def get_parameters(self):
        parameters = self.request_son.copy()

        try:
            parameters['min_constituents'] = int(
                parameters.get('min_constituents', MIN_CONSITUENTS))
        except ValueError:
            raise errors.ModelError("Invalid minimum number of constituents")

        if 'approval' not in parameters:
            raise errors.ModelError("Approval status required")

        interval = Interval.from_parameters(parameters)
        parameters.min_date = interval.lower_bound(
            datetime.datetime.utcfromtimestamp(parameters.get('min_date')))
        parameters.max_date = interval.upper_bound(
            datetime.datetime.utcfromtimestamp(parameters.get('max_date')))

        self.reason("Date range: %s - %s" % (
            parameters.min_date.strftime('%d %b %Y'),
            parameters.max_date.strftime('%d %b %Y')))

        return parameters

    @run_on_executor
    def process_temporal(
            self, parameters, survey_id, tmpdir, extension, surveygroup_ids):
        with model.session_scope() as session:
            query = self.build_query(session, parameters, survey_id)
            responses = query.all()

            info = []
            if surveygroup_ids is not None:
                surveygroups = (
                    session.query(model.SurveyGroup)
                    .filter(model.SurveyGroup.id.in_(surveygroup_ids)))
                responses, filter_info = self.filter_by_surveygroup(
                    responses, surveygroups)
                info.extend(filter_info)

            responses, filter_info = self.filter_deleted_structure(responses)
            info.extend(filter_info)

            interval = Interval.from_parameters(parameters)
            bucketer = TemporalResponseBucketer(interval)
            for response in responses:
                bucketer.add(response)
            table_meta = bucketer.to_table_meta()
            rows = self.create_detail_rows(table_meta)

            if parameters.type == 'summary':
                report_type = 'summary'
                organisation = (
                    session
                    .query(model.Organisation)
                    .get(parameters.organisation_id))
                rows = self.convert_to_stats(
                    rows, organisation, parameters.min_constituents)
            else:
                report_type = 'detail'

            cols, rows = self.create_table(rows, table_meta, report_type)

        if extension == 'xlsx':
            outfile = "%s.xlsx" % report_type
            outpath = os.path.join(tmpdir, outfile)
            writer = XlWriter(outpath)
        else:
            raise errors.MissingDocError(
                "File type not supported: %s" % extension)

        writer.write(cols, rows, parameters, info)

        return outpath, outfile, info

    def build_query(self, session, parameters, survey_id):
        # All responses to current survey
        query = (
            session.query(model.Response)
            .options(joinedload('submission'))
            .options(joinedload('submission.organisation'))
            .options(joinedload('qnode_measure'))
            .join(model.Submission)
            .join(model.Survey)
            .join(model.Organisation)
            .filter(model.Submission.survey_id == survey_id)
            .filter(~model.Submission.deleted)
            .filter(~model.Survey.deleted)
            .order_by(
                model.Response.measure_id,
                model.Submission.organisation_id,
                model.Submission.created))

        def date_filter(query):
            return (
                query
                .filter(model.Submission.created >= parameters.min_date)
                .filter(model.Submission.created < parameters.max_date))

        def quality_filter(query):
            quality = parameters.quality
            return query.filter(model.Response.quality >= quality)

        def approval_filter(query):
            approval = parameters.approval
            approval_index = APPROVAL_STATES.index(approval)
            included_approval_states = APPROVAL_STATES[approval_index:]
            return query.filter(
                model.Submission.approval.in_(included_approval_states))

        def location_filter(query):
            query = query.join(model.OrgLocation)
            union_loc_filter = false()

            for loc in parameters.locations:
                loc_filter = true()
                if loc.country:
                    loc_filter &= model.OrgLocation.country == loc.country
                if loc.state:
                    loc_filter &= model.OrgLocation.state == loc.state
                if loc.region:
                    loc_filter &= model.OrgLocation.region == loc.region
                if loc.county:
                    loc_filter &= model.OrgLocation.county == loc.county
                if loc.city:
                    loc_filter &= model.OrgLocation.city == loc.city
                if loc.postcode:
                    loc_filter &= model.OrgLocation.postcode == loc.postcode
                if loc.suburb:
                    loc_filter &= model.OrgLocation.suburb == loc.suburb
                union_loc_filter |= loc_filter
            return query.filter(union_loc_filter)

        def size_filter(query):
            query = query.join(model.OrgMeta)

            if parameters.min_internal_ftes:
                min_ftes = parameters.min_internal_ftes
                query = query.filter(
                    model.OrgMeta.number_fte >= min_ftes)
            if parameters.max_internal_ftes:
                max_ftes = parameters.max_internal_ftes
                query = query.filter(
                    model.OrgMeta.number_fte <= max_ftes)

            if parameters.min_external_ftes:
                min_ftes = parameters.min_external_ftes
                query = query.filter(
                    model.OrgMeta.number_fte_ext >= min_ftes)
            if parameters.max_external_ftes:
                max_ftes = parameters.max_external_ftes
                query = query.filter(
                    model.OrgMeta.number_fte_ext <= max_ftes)

            if parameters.min_employees:
                min_employees = parameters.min_employees
                query = query.filter(
                    (model.OrgMeta.number_fte +
                        model.OrgMeta.number_fte_ext) >= min_employees)
            if parameters.max_employees:
                max_employees = parameters.max_employees
                query = query.filter(
                    (model.OrgMeta.number_fte +
                        model.OrgMeta.number_fte_ext) <= max_employees)

            if parameters.min_population:
                min_population = parameters.min_population
                query = query.filter(
                    model.OrgMeta.population_served >= min_population)
            if parameters.max_population:
                max_population = parameters.max_population
                query = query.filter(
                    model.OrgMeta.population_served <= max_population)

            return query

        query = date_filter(query)
        query = approval_filter(query)
        if parameters.quality:
            query = quality_filter(query)
        if parameters.locations:
            query = location_filter(query)
        if parameters.filter_size:
            query = size_filter(query)
        return query

    def filter_by_surveygroup(self, responses, surveygroups):
        excluded_orgs = set()
        excluded_programs = set()
        filtered_responses = []
        for r in responses:
            org = r.submission.organisation
            program = r.submission.program
            assert r.surveygroups == (org.surveygroups & program.surveygroups)
            if org in excluded_orgs:
                continue
            elif org.surveygroups.isdisjoint(surveygroups):
                excluded_orgs.add(org)
                continue

            if program in excluded_programs:
                continue
            elif program.surveygroups.isdisjoint(surveygroups):
                excluded_programs.add(program)
                continue
            filtered_responses.append(r)

        info = []
        if excluded_orgs:
            info.append(
                "Excluded %d organisation(s) that are not in your survey "
                "groups" % len(excluded_orgs))
        if excluded_programs:
            info.append(
                "Excluded %d program(s) that are not in your survey "
                "groups" % len(excluded_programs))
        return filtered_responses, info

    def filter_deleted_structure(self, responses):
        deleted_things = keydefaultdict(
            lambda t: t.closest_deleted_ancestor() is not None)
        filtered_responses = [
            r for r in responses
            if not deleted_things[r.qnode_measure]]
        return filtered_responses, []

    def create_detail_rows(self, table_meta):
        '''
        @return a list of OrganisationRows. These need further transformation
            before they can be rendered; see OrganisationRow for details. The
            rows are sorted in the same way as the keys in `table_meta`.
        '''
        rows = []
        # Measure varies the most slowly, then organisation, then temporal
        # bucket.
        qm_rowset = []
        measure_id = None
        org_id = None
        n_parts = 0
        qm_rows = None
        org_rows = None

        def commit_rowset():
            qm_rowset.sort(key=lambda org_row: org_row.qm_row.part_i)
            rows.extend(qm_rowset)
            qm_rowset.clear()

        for qm, organisation, bucket in table_meta.keys():
            if measure_id != qm.measure_id:
                commit_rowset()
                measure_id = qm.measure_id
                n_parts = table_meta.part_lengths[measure_id]
                qm_rows = [QnodeMeasureRow(qm, -1)]
                qm_rows.extend(QnodeMeasureRow(qm, i) for i in range(n_parts))
                org_id = None

            if org_id != organisation.id:
                org_id = organisation.id
                org_rows = [
                    OrganisationRow(qm_row, organisation)
                    for qm_row in qm_rows]
                qm_rowset.extend(org_rows)

            k = (qm, organisation, bucket)
            response = table_meta.get(k)
            for org_row in org_rows:
                org_row.append(response)
            if response is not None:
                for qm_row in qm_rows:
                    qm_row.update(response.qnode_measure)

        commit_rowset()

        return rows

    def convert_to_stats(self, rows, organisation, min_constituents):
        out_rows = []
        for qm_row, org_rows in itertools.groupby(
                rows, key=lambda r: r.qm_row):

            org_rows = list(org_rows)

            dataset = [row.data() for row in org_rows]
            cells = list(zip(*dataset))
            stats = [self.compute_stats(c, min_constituents) for c in cells]
            stats = list(zip(*stats))
            try:
                out_rows.append(next(
                    org_row for org_row in org_rows
                    if org_row.organisation == organisation))
            except StopIteration:
                out_rows.append(OrganisationRow(qm_row, organisation))
            out_rows.append(StatisticRow(
                qm_row, "Min", list(stats[0])))
            out_rows.append(StatisticRow(
                qm_row, "1st Quartile", list(stats[1])))
            out_rows.append(StatisticRow(
                qm_row, "Median", list(stats[2])))
            out_rows.append(StatisticRow(
                qm_row, "3rd Quartile", list(stats[3])))
            out_rows.append(StatisticRow(
                qm_row, "Max", list(stats[4])))
            out_rows.append(StatisticRow(
                qm_row, "Consituents", list(stats[5])))

        return out_rows

    def compute_stats(self, cells, min_constituents):
        # TODO: for multiple-choice, show categorical spread of answers
        constituents = [c for c in cells if isinstance(c, Number)]
        if len(constituents) < min_constituents:
            return (None,) * 5 + (0,)
        np_columns = np.array(constituents)
        results = (
            min(np_columns),
            np.percentile(np_columns, 25),
            np.percentile(np_columns, 50),
            np.percentile(np_columns, 75),
            max(np_columns),
            len(constituents),
        )

        return results

    def create_table(self, rows, table_meta, report_type):
        base_url = "%s://%s" % (self.request.protocol, self.request.host)
        out_rows = []
        for row in rows:
            out_rows.append(row.headers(base_url) + row.data())

        if report_type == 'detail':
            statistic_name = "Organisation"
        else:
            statistic_name = "Statistic"
        cols = [
            ("Order", 5, 'text'),
            ("Latest program", 15, 'text'),
            ("Path", 10, 'text'),
            ("Measure", 40, 'text'),
            ("Part", 20, 'text'),
            (statistic_name, 30, 'text'),
            ("Link", 10, 'text'),
        ] + [(b, 12, 'real') for b in table_meta.buckets]

        return cols, out_rows


class XlWriter:
    def __init__(self, outpath):
        self.outpath = outpath

    def write(self, cols, rows, parameters, info):
        with xlsxwriter.Workbook(self.outpath) as workbook:
            cell_formats = self.make_formats(workbook)
            self.write_meta(parameters, info, workbook, cell_formats)
            self.write_data(cols, rows, workbook, cell_formats)

    def make_formats(self, workbook):
        cell_formats = {
            'text_header': workbook.add_format({'bold': 1}),
            'date_header': workbook.add_format(
                {'num_format': 'dd/mm/yyyy', 'bold': 1}),
            'date': workbook.add_format({'num_format': 'dd/mm/yyyy'}),
            'text': workbook.add_format({}),
            'link': workbook.add_format(
                {'font_color': 'blue', 'underline':  1}),
            'real': workbook.add_format(
                {'num_format': '0.00', 'align': 'right'}),
            'int': workbook.add_format(
                {'num_format': '0', 'align': 'right'}),
        }
        return cell_formats

    def write_meta(self, parameters, info, workbook, cell_formats):
        worksheet = workbook.add_worksheet("Parameters")
        worksheet.set_column(0, 0, 25, cell_formats['text_header'])
        worksheet.set_column(1, 1, 12)

        row_gen = itertools.count()
        for name in sorted(parameters):
            value = parameters[name]
            if name in {'min_date', 'max_date'}:
                value_format = cell_formats['date']
            else:
                value_format = None

            if name == 'locations':
                for item in value:
                    row = next(row_gen)
                    worksheet.write(row, 0, 'location')
                    worksheet.write(row, 1, item.description, value_format)
            else:
                row = next(row_gen)
                worksheet.write(row, 0, name)
                worksheet.write(row, 1, value, value_format)

        for message in info:
            row = next(row_gen)
            worksheet.write(row, 0, 'Info')
            worksheet.write(row, 1, message)

    def write_data(self, cols, rows, workbook, cell_formats):
        worksheet = workbook.add_worksheet("Data")
        worksheet.freeze_panes(1, 0)

        # Write column headings
        for i, col in enumerate(cols):
            heading, cell_width, data_type = col
            if isinstance(heading, datetime.datetime):
                header_format = cell_formats['date_header']
            else:
                header_format = cell_formats['text_header']
            worksheet.set_column(i, i, cell_width, cell_formats[data_type])
            worksheet.write(0, i, heading, header_format)

        # Write data, this depends on requested report type.
        for row_index, row in enumerate(rows, 1):
            for col_index, (col, cell) in enumerate(zip(cols, row)):
                if isinstance(cell, Link):
                    worksheet.write_url(
                        row_index, col_index, cell.url, None, cell.title)
                elif isinstance(cell, int) and col[2] != 'int':
                    worksheet.write(
                        row_index, col_index, cell, cell_formats['int'])
                else:
                    worksheet.write(row_index, col_index, cell)


class Interval:
    def __init__(self, width, units):
        self.width = width
        self.units = units

    @classmethod
    def from_parameters(cls, parameters):
        try:
            width = int(parameters.get('interval_num', 1))
        except ValueError:
            raise errors.ModelError("Invalid interval")
        units = parameters.get('interval_unit', 'months')

        if units == 'years':
            if width < 1:
                raise errors.ModelError("Interval must be at least one year")
        elif units == 'months':
            if width not in {1, 2, 3, 6}:
                raise errors.ModelError("Interval must be 1, 2, 3 or 6 months")
        else:
            raise errors.ModelError("Unrecognised interval %s" % units)
        return cls(width, units)

    def temporal_bucket(self, date):
        # Align buckets to Gregorian epoch
        if self.units == 'years':
            return date.year // self.width
        else:
            return (date.year * 12 + (date.month - 1)) // self.width

    def lower_bound_of_bucket(self, bucket_i):
        if self.units == 'years':
            year = bucket_i * self.width
            return datetime.datetime(year, 1, 1)
        else:
            year = (bucket_i * self.width) // 12
            month = ((bucket_i * self.width) % 12) + 1
            return datetime.datetime(year, month, 1)

    def lower_bound(self, date):
        bucket_i = self.temporal_bucket(date)
        return self.lower_bound_of_bucket(bucket_i)

    def upper_bound(self, date):
        bucket_i = self.temporal_bucket(date)
        bucket_i += 1
        return self.lower_bound_of_bucket(bucket_i)


class TableMeta:
    '''
    Bucketed responses sorted by measure, organisation and time.
    '''

    def __init__(
            self, bucketed_responses, qnode_measures, part_lengths,
            organisations, buckets):
        self.bucketed_responses = bucketed_responses
        self.qnode_measures = qnode_measures
        self.part_lengths = part_lengths
        self.organisations = organisations
        self.buckets = buckets

    def keys(self):
        return itertools.product(
            self.qnode_measures, self.organisations, self.buckets)

    def __getitem__(self, k):
        response = self.get(k)
        if response is None:
            raise KeyError("No such response %s", k)
        return response

    def get(self, k, default=None):
        qm, organisation, bucket = k
        k = (qm.measure_id, organisation.id, bucket)
        return self.bucketed_responses.get(k, default)

    def __iter__(self):
        return iter(self.keys())

    def __len__(self):
        return len(self.bucketed_responses)


class TemporalResponseBucketer:
    '''
    Buckets responses by measure, organisation and time.
    '''

    def __init__(self, interval):
        self.interval = interval
        self.bucketed_responses = {}
        self.buckets = set()
        self.qnode_measure_map = {}
        self.part_lengths = defaultdict(lambda: 0)
        self.organisations = set()

    def add(self, response):
        bucket = self.interval.lower_bound(response.submission.created)
        mid = response.measure_id
        k = (mid, response.submission.organisation.id, bucket)

        if k in self.bucketed_responses:
            if (self.bucketed_responses[k].submission.created >
                    response.submission.created):
                return

        self.bucketed_responses[k] = response

        self.buckets.add(bucket)
        self.qnode_measure_map[mid] = response.qnode_measure
        n_parts = len(response.measure.response_type.parts)
        self.part_lengths[mid] = max(self.part_lengths[mid], n_parts)
        self.organisations.add(response.submission.organisation)

    def to_table_meta(self):
        buckets = sorted(self.buckets)
        qnode_measures = sorted(
            self.qnode_measure_map.values(),
            key=lambda qm: qm.get_path_tuple())
        organisations = sorted(
            self.organisations, key=lambda o: o.name)
        return TableMeta(
            self.bucketed_responses.copy(), qnode_measures,
            dict(self.part_lengths), organisations, buckets)


class QnodeMeasureRow:
    def __init__(self, qm, part_i):
        self.qm = qm
        self.part_i = part_i
        self.response_type = None
        self.part_name = "Score"
        self.update(qm)

    def update(self, qm):
        if self.part_i < 0:
            return
        # If the program changes, the response parts may change.
        assert(qm.measure_id == self.qm.measure_id)
        rt = qm.measure.response_type
        if rt != self.response_type and len(rt.parts) > self.part_i:
            if 'name' in rt.parts[self.part_i]:
                self.part_name = rt.parts[self.part_i]['name']
            else:
                self.part_name = 'Part %d' % (self.part_i + 1)

    def headers(self):
        path = self.path(False)
        sort_path = self.path(True)
        program_title = self.qm.program.title
        measure_title = self.qm.measure.title
        return [sort_path, program_title, path, measure_title, self.part_name]

    def path(self, for_sort=False):
        if for_sort:
            fmt = "%04d"
        else:
            fmt = "%d"
        base_path = ".".join(fmt % seq for seq in self.qm.get_path_tuple())
        part_i = self.part_i
        if part_i < 0 and not for_sort:
                return base_path
        return base_path + ":" + (fmt % (part_i + 1))

    def link(self, base_url):
        return Link(
            "Measure",
            "{}/#/2/measure/{}?program={}&survey={}".format(
                base_url, self.qm.measure_id, self.qm.program_id,
                self.qm.survey_id))


class OrganisationRow:
    def __init__(self, qm_row, organisation):
        self.qm_row = qm_row
        self.organisation = organisation
        self.responses = []
        self.latest_response = None

    def append(self, response):
        self.responses.append(response)
        if response is not None:
            self.latest_response = response

    def headers(self, base_url):
        return self.qm_row.headers() + [
            self.organisation.name, self.link(base_url)]

    def data(self):
        return [
            self.get_part(response)
            for response in self.responses]

    def get_part(self, response):
        if response is None:
            return None
        if self.qm_row.part_i < 0:
            return response.score
        if response.not_relevant:
            return "NA"
        try:
            part = response.response_parts[self.qm_row.part_i]
        except (IndexError, TypeError):
            return None
        try:
            return "%d. %s" % (part['index'] + 1, part['note'])
        except KeyError:
            return part.get('value', None)

    def link(self, base_url):
        if self.latest_response is not None:
            return Link(
                "Response",
                "{}/#/2/measure/{}?submission={}".format(
                    base_url, self.latest_response.measure_id,
                    self.latest_response.submission.id))
        else:
            return self.qm_row.link(base_url)


class StatisticRow:
    def __init__(self, qm_row, name, data):
        self.qm_row = qm_row
        self.name = name
        self._data = data

    def headers(self, base_url):
        return self.qm_row.headers() + [self.name, self.qm_row.link(base_url)]

    def data(self):
        return self._data


class Link:
    __slots__ = ('title', 'url')

    def __init__(self, title, url):
        self.title = title
        self.url = url
