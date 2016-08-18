import datetime
import itertools
import logging

import tornado.web
from sqlalchemy.orm import joinedload

import handlers
import model


log = logging.getLogger('app.report.temporal')


class TemporalReportHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, survey_id, extension):

        organisation_id = self.get_argument('organisationId', '')

        with model.session_scope() as session:
            if organisation_id:
                pass

            query = (session.query(model.Response)
                    .options(joinedload('submission'))
                    .options(joinedload('submission.organisation'))
                    .options(joinedload('measure'))
                    .join(model.Submission)
                    .filter(model.Submission.survey_id == survey_id)
                    .order_by(model.Response.measure_id,
                        model.Submission.organisation_id,
                        model.Submission.created))

            responses = query.all()

            bucketed_responses = {}
            buckets = set()
            measures = set()
            organisations = set()
            for response in responses:
                bucket = self.lower_bound(response.submission.created)
                k = (response.measure, response.submission.organisation,
                    bucket)

                if k in bucketed_responses:
                    if (bucketed_responses[k].submission.created
                            > response.submission.created):
                        continue

                bucketed_responses[k] = response

                buckets.add(bucket)
                measures.add(response.measure)
                organisations.add(response.submission.organisation)

            buckets = sorted(buckets)
            measures = sorted(measures, key=lambda m: m.get_path(survey_id))
            organisations = sorted(organisations, key=lambda o: o.name)

            rows = []
            current_row = None
            current_measure = None
            current_organisation = None
            for k in itertools.product(measures, organisations, buckets):
                r = bucketed_responses[k]
                if r.measure != current_measure or r.submission.organisation != current_organisation:
                    current_measure = r.measure
                    current_organisation = r.submission.organisation
                    current_row = [
                        r.measure.get_path(survey_id),
                        r.submission.organisation.name]
                    rows.append(current_row)
                current_row.append(r.score)

        import pprint
        self.set_header("Content-Type", "text/plain")
        self.write(pprint.pformat(rows))
        self.finish()


    def lower_bound(self, date):
        return date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
