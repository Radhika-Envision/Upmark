from concurrent.futures import ThreadPoolExecutor
import datetime
import time
import uuid
import json

from tornado import gen
from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.session import make_transient

import crud.survey
import handlers
import model
import logging

from utils import reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.statistics')


class FunctionHandler(handlers.Paginate, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, survey_id):
        with model.session_scope() as session:
            try:
                responseNodes = session.query(model.ResponseNode)\
                    .filter(survey_id==survey_id)

                if responseNodes is None:
                    raise ValueError("No such object")
                # if assessment.organisation.id != self.organisation.id:
                #     self.check_privillege('author', 'consultant')
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such assessment")



            response = []
            for responseNode in responseNodes:
                if responseNode.qnode.parent == None:
                    r = [res for res in response if res["seq"] == (responseNode.qnode.seq + 1)]
                    log.info("r: %s", r)
                    if len(r) == 0:
                        r = {
                            "min": 0,
                            "max": 20000,
                            "org_max": 0,
                            "org_min": 20000,
                            "org_median": 0,
                            "count": 0,
                            "total": 0
                        }
                        response.append(r)
                    else:
                        r = r[0]
                    log.info("response: %s", response)
                    log.info("r: %s", r)

                    log.info("responseNode.score: %s", responseNode.score)
                    log.info("responseNode.seq: %s", responseNode.qnode.seq)
                    if r["org_min"] > responseNode.score:
                        r["org_min"] = responseNode.score
                    if r["org_max"] < responseNode.score:
                        r["org_max"] = responseNode.score
                    r["count"] += 1
                    r["total"] += responseNode.score
                    r["seq"] = responseNode.qnode.seq + 1
                    r["org_median"] = r["total"] / r["count"]
                    log.info("response: %s", response)

        self.set_header("Content-Type", "application/json")
        # self.write(json_encode(son))
        self.write(json.dumps(response))
        self.finish()
