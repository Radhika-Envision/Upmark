import json

import numpy
from sqlalchemy.orm import joinedload
import tornado.web

import handlers
import model
import logging


log = logging.getLogger('app.report.sub_stats')


class StatisticsHandler(handlers.Paginate, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, program_id, survey_id):
        if self.has_privillege('consultant') or self.has_privillege('authority') :
            pass
        else:
            with model.session_scope() as session:
                purchased_survey = (session.query(model.PurchasedSurvey)
                    .filter_by(program_id=program_id,
                               survey_id=survey_id,
                               organisation_id=self.organisation.id)
                    .first())
                log.info("purchased_survey: %s", purchased_survey)
                if purchased_survey==None:
                    raise handlers.AuthzError(
                        "You should purchase this survey to see this chart")

        parent_id = self.get_argument("parentId", None)
        approval=self.get_argument("approval", "draft")
        approval_states = ['draft', 'final', 'reviewed', 'approved']
        approval_index = approval_states.index(approval)
        included_approval_states=approval_states[approval_index:]
        with model.session_scope() as session:
            survey = (session.query(model.Survey)
                .filter(model.Survey.id == survey_id,
                        model.Survey.program_id == program_id)
                .first())
            if not survey:
                raise handlers.MissingDocError("No such survey")
            min_approval_index = approval_states.index(survey.min_stats_approval)
            if min_approval_index > approval_index:
                raise handlers.AuthzError(
                    "Can't display data for that approval state")

            responseNodes = (session.query(model.ResponseNode)
                .join(model.ResponseNode.qnode)
                .join(model.ResponseNode.submission)
                .options(joinedload(model.ResponseNode.qnode))
                .filter(model.ResponseNode.program_id == program_id,
                        model.QuestionNode.survey_id == survey_id,
                        model.QuestionNode.parent_id == parent_id,
                        model.Submission.approval.in_(included_approval_states),
                        model.Submission.deleted == False,
                        model.QuestionNode.deleted == False))

            response = []
            for responseNode in responseNodes:
                r = [res for res in response
                     if res["qnodeId"] == str(responseNode.qnode.id)]
                if len(r) == 0:
                    r = { "qnodeId": str(responseNode.qnode.id),
                        "title": str(responseNode.qnode.title),
                        "data": [] }
                    response.append(r)
                else:
                    r = r[0]

                r["data"].append(responseNode.score)

            for r in response:
                data = r["data"]
                r["min"] = min(data)
                r["max"] = max(data)
                r["count"] = len(data)
                numpy_array = numpy.array(data)
                # r["std"] = numpy.std(numpy_array)
                r["quartile"] = [numpy.percentile(numpy_array, 25),
                                numpy.percentile(numpy_array, 50),
                                numpy.percentile(numpy_array, 75)]

        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(response))
        self.finish()
