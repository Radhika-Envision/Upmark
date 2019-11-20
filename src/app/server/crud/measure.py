import re
import datetime
import json
from tornado.escape import json_encode
import tornado.web
from sqlalchemy import cast, String
from sqlalchemy.orm import joinedload
from sqlalchemy import func
import sqlalchemy
import voluptuous.error

from activity import Activities
import base_handler
from cache import instance_method_lru_cache
import errors
import logging
import model
from response_type import ResponseType
from score import Calculator
from utils import falsy, reorder, ToSon, truthy, updater
from response_type import ResponseTypeError
from crud.response import ResponseHandler

log = logging.getLogger('app.crud.measure')


class MeasureHandler(base_handler.Paginate, base_handler.BaseHandler):

    @tornado.web.authenticated
    def get(self, measure_id):
        if not measure_id:
            self.query()
            return

        '''Get a single measure.'''
        program_id = self.get_argument('programId', '')
        survey_id = self.get_argument('surveyId', '')
        if not program_id:
            raise errors.MissingDocError("Missing program ID")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = (
                session.query(model.Program)
                .options(joinedload('surveygroups'))
                .get(program_id))
            if not program:
                raise errors.MissingDocError("No such program")

            if survey_id:
                survey = session.query(model.Survey).get(
                    (survey_id, program_id))
            else:
                survey = None

            query = (
                session.query(model.Measure)
                .filter(model.Measure.id == measure_id)
                .filter(model.Measure.program_id == program_id))
            if survey_id:
                query = (
                    query
                    .join(model.QnodeMeasure)
                    .filter(model.QnodeMeasure.survey_id == survey_id))

            measure = query.first()
            if not measure:
                raise errors.MissingDocError("No such measure")

            policy = user_session.policy.derive({
                'program': program,
                'survey': survey,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('measure_view')

            to_son = ToSon(
                # Fields to match from any visited object
                r'/ob_type$',
                r'/id$',
                r'/title$',
                r'/seq$',
                r'/deleted$',
                r'/program_id$',
                r'/program/tracking_id$',
                r'/program/created$',
                r'<^/description$',
                r'^/weight$',
                r'^/response_type_id$',
                r'/parent$',
                r'/parents$',
                r'/parents/[0-9]+$',
                r'/survey$',
                r'/survey/program$',
                r'/survey/structure.*$',
                r'/has_quality$',
                r'/is_editable$',
            )
            son = to_son(measure)
            if measure.response_type_id:
                measure_responeType=self.get_responseType(measure.response_type_id, program_id)
                son['responseType']=measure_responeType
            # response_types=json.load(measure_responeType.parts)
            submeasureIdList=[]
            for p in measure_responeType.parts:
                if p.submeasure and (not (p.submeasure in submeasureIdList)):
                     submeasureIdList.append(p.submeasure)
            if len(submeasureIdList) >0:
               son['subMeasureList']=self.get_measureList(submeasureIdList, program_id, survey_id)



            if survey_id:
                qnode_measure = measure.get_qnode_measure(survey_id)

                to_son = ToSon(
                    r'/id$',
                    r'/ob_type$',
                    r'/seq$',
                    r'/title$',
                    r'^/error$',
                    r'/qnode$',
                    r'/parent$',
                    r'/deleted$',
                    r'/survey$',
                    r'/survey/program$',
                    r'/is_editable$',
                    r'/survey/structure.*$',
                    r'/survey/program_id$',
                    r'/survey/program/tracking_id$',
                    r'/survey/program/created$',
                    r'/has_quality$',
                )
                son.update(to_son(qnode_measure))
                son['parent'] = son['qnode']
                del son['qnode']

                # Variables, handled separately to avoid excessive recursion
                to_son = ToSon()
                son['sourceVars'] = to_son([{
                    'source_measure': {
                        'id': mv.source_qnode_measure.measure_id,
                        'title': mv.source_qnode_measure.measure.title,
                        'declared_vars': self.get_declared_vars(
                            mv.source_qnode_measure.measure)
                    },
                    'source_field': mv.source_field,
                    'target_field': mv.target_field,
                } for mv in qnode_measure.source_vars])
                son['targetVars'] = to_son([{
                    'target_measure': {
                        'id': mv.target_qnode_measure.measure_id,
                        'title': mv.target_qnode_measure.measure.title,
                    },
                    'source_field': mv.source_field,
                    'target_field': mv.target_field,
                } for mv in qnode_measure.target_vars])

                QnodeMeasure = model.QnodeMeasure
                prev = (
                    session.query(QnodeMeasure)
                    .filter(QnodeMeasure.qnode_id == qnode_measure.qnode_id,
                            QnodeMeasure.program_id == measure.program_id,
                            QnodeMeasure.seq < son['seq'])
                    .order_by(QnodeMeasure.seq.desc())
                    .first())
                next_ = (
                    session.query(QnodeMeasure)
                    .filter(QnodeMeasure.qnode_id == qnode_measure.qnode_id,
                            QnodeMeasure.program_id == measure.program_id,
                            QnodeMeasure.seq > son['seq'])
                    .order_by(QnodeMeasure.seq)
                    .first())

                if prev is not None:
                    son['prev'] = str(prev.measure_id)
                if next_ is not None:
                    son['next'] = str(next_.measure_id)

            else:
                son['program'] = to_son(measure.program)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        '''Get a list.'''
        qnode_id = self.get_argument('qnodeId', '')
        submission_id=self.get_argument('submissionId', '')
        if qnode_id != ''  and not submission_id:
            self.query_children_of(qnode_id)
            return
        if qnode_id != ''  and submission_id != '':
            self.query_measures_submission(qnode_id, submission_id)
            return
        orphan = self.get_argument('orphan', '')
        term = self.get_argument('term', '')
        program_id = self.get_argument('programId', '')
        survey_id = self.get_argument('surveyId', '')
        with_declared_variables = truthy(self.get_argument(
            'withDeclaredVariables', ''))

        to_son = ToSon(
            # Fields to match from any visited object
            r'/ob_type$',
            r'/id$',
            r'/title$',
            r'/parent$',
            r'/parents$',
            r'/parents/[0-9]+$',
            r'/seq$',
            r'/weight$',
            r'/deleted$',
            r'/program/tracking_id$',
            # Descend into nested objects
            r'/[0-9]+$',
            r'/program$',
        )

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = (
                session.query(model.Program)
                .options(joinedload('surveygroups'))
                .get(program_id))
            if not program:
                raise errors.MissingDocError("No such program")

            if survey_id:
                survey = (
                    session.query(model.Survey).get([survey_id, program_id]))
            else:
                survey = None

            policy = user_session.policy.derive({
                'survey': survey,
                'program': program,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('measure_view')

            if orphan != '' and truthy(orphan):
                # Orphans only
                # previous version: not consider submeasure
                #query = (
                #    session.query(model.Measure)
                #    .outerjoin(model.QnodeMeasure)
                #    .filter(model.Measure.program_id == program_id)
                #    .filter(model.QnodeMeasure.qnode_id == None))
                
                # current version: not display submeasure
                query = (
                    session.query(model.Measure)
                    .outerjoin(model.QnodeMeasure)
                    .filter(model.Measure.id == model.QnodeMeasure.measure_id) # only measure
                    .filter(model.Measure.program_id == program_id)
                    .filter(model.QnodeMeasure.qnode_id == None))    
            elif orphan != '' and falsy(orphan):
                # Non-orphans only
                # previous version: not consider submeasure               
                #query = (
                #    session.query(model.Measure)
                #    .join(model.QnodeMeasure)
                #    .filter(model.Measure.program_id == program_id))
                # current version: not display submeasure
                query = (
                    session.query(model.Measure)
                    .join(model.QnodeMeasure)
                    .filter(model.Measure.id == model.QnodeMeasure.measure_id) # only measure
                    .filter(model.Measure.program_id == program_id))                    
            else:
                # All measures
                # previous version: not consider submeasure                 
                #query = (
                #    session.query(model.Measure)
                #    .filter_by(program_id=program_id))
                # current version: not display submeasure
                query = (
                    session.query(model.Measure)
                    .join(model.QnodeMeasure)                                  # only measure
                    .filter(model.Measure.id == model.QnodeMeasure.measure_id) # only measure
                    .filter_by(program_id=program_id))
            rt_term = None
            if term:
                plain_parts = []
                for part in term.split(' '):
                    if part.startswith('rt:'):
                        rt_term = part[3:]
                    else:
                        plain_parts.append(part)
                term = ' '.join(plain_parts)

            if term:
                query = query.filter(
                    model.Measure.title.ilike(r'%{}%'.format(term)))

            if rt_term:
                query = (
                    query
                    .join(model.ResponseType)
                    .filter(
                        (cast(model.ResponseType.id, String) == rt_term) |
                        (model.ResponseType.name.ilike(
                            r'%{}%'.format(rt_term)))
                    ))

            if with_declared_variables:
                query = query.options(joinedload('response_type'))

            if survey_id:
                query = (
                    query
                    .options(joinedload('qnode_measures'))
                    .join(model.QnodeMeasure)
                    .filter(model.QnodeMeasure.survey_id == survey_id))

            if self.get_argument('noPage', None) is None:
                query = self.paginate(query)

            measures = query.all()
            sons = to_son(measures)

            to_son = ToSon(
                r'/ob_type$',
                r'/id$',
                r'/seq$',
                r'/title$',
                r'^/error$',
                r'/qnode$',
                r'/parent$',
                r'/survey$',
                r'/survey/program$',
                r'/is_editable$',
                r'/survey/structure.*$',
                r'/survey/program_id$',
                r'/survey/program/tracking_id$',
                r'/survey/program/created$',
                r'/has_quality$',
            )

            for mson, measure in zip(sons, measures):
                mson['orphan'] = len(measure.qnode_measures) == 0
                if survey_id:
                    qnode_measure = measure.get_qnode_measure(survey_id)
                    mson.update(to_son(qnode_measure))
                    mson['error'] = qnode_measure.error
                    mson['parent'] = mson['qnode']
                    del mson['qnode']
                if with_declared_variables:
                    mson['declaredVars'] = self.get_declared_vars(measure)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    I_REGEX = re.compile(r'(.*)__i')

    def get_declared_vars(self, measure):
        response_type = self.get_response_type(measure.response_type)
        return ['_raw', '_score', '_weight'] + response_type.declared_vars
        # declared_vars = [
        #     {'id': '_raw', 'name': "Raw score"},
        #     {'id': '_score', 'name': "Weighted score"},
        #     {'id': '_weight', 'name': "Measure weight"},
        # ]
        # for v in response_type.declared_vars:
        #     match = MeasureHandler.I_REGEX.match(v)
        #     if match:
        #         declared_vars.append({
        #             'id': v,
        #             'name': "%s (index)" % match.group(1)})
        #     else:
        #         declared_vars.append({'id': v, 'name': v})
        # return declared_vars

    @instance_method_lru_cache()
    def get_response_type(self, response_type):
        return ResponseType(
            response_type.name, response_type.parts, response_type.formula)

    def query_children_of(self, qnode_id):
        program_id = self.get_argument('programId', '')
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            # Only children of a certain qnode
            qnode = (
                session.query(model.QuestionNode)
                .options(joinedload('survey'))
                .options(joinedload('program'))
                .options(joinedload('program.surveygroups'))
                .get((qnode_id, program_id)))

            if not qnode:
                raise errors.MissingDocError("No such category")

            policy = user_session.policy.derive({
                'survey': qnode.survey,
                'program': qnode.program,
                'surveygroups': qnode.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('measure_view')

            to_son = ToSon(
                # Fields to match from any visited object
                r'/ob_type$',
                r'/id$',
                r'/title$',
                r'^/error$',
                r'/qnode$',
                r'/parent$',
                r'/parents$',
                r'/parents/[0-9]+$',
                r'/seq$',
                r'/weight$',
                r'/deleted$',
                r'/program/tracking_id$',
                # Descend into nested objects
                r'/[0-9]+$',
                r'/program$',
                r'/survey$',
                r'/survey/structure.*$',
                r'/survey/program$',
            )
            sons = []
            for qm in qnode.qnode_measures:
                ## get submeasures ***************
                n_submeasures=0
                subId= None
                if qm.measure and qm.measure.response_type and qm.measure.response_type.parts:
                    for p in qm.measure.response_type.parts:
                        if  'submeasure' not in p:
                            break
                        if p['submeasure'] != subId:
                           n_submeasures = n_submeasures + 1
                        subId=p['submeasure']
                ## get submeasures *************** 
                mson = to_son(qm.measure)
                mson.update(to_son(qm))
                mson['n_submeasures'] = n_submeasures
                mson['parent'] = mson['qnode']
                del mson['qnode']
                sons.append(mson)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    def query_measures_submission(self, qnode_id, submission_id):
        program_id = self.get_argument('programId', '')
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            # Only children of a certain qnode
            qnode = (
                session.query(model.QuestionNode)
                .options(joinedload('survey'))
                .options(joinedload('program'))
                .options(joinedload('program.surveygroups'))
                .get((qnode_id, program_id)))

            if not qnode:
                raise errors.MissingDocError("No such category")

            policy = user_session.policy.derive({
                'survey': qnode.survey,
                'program': qnode.program,
                'surveygroups': qnode.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('measure_view')

            to_son = ToSon(
                # Fields to match from any visited object
                r'/ob_type$',
                r'/id$',
                r'/title$',
                r'^/error$',
                r'/qnode$',
                r'/parent$',
                r'/parents$',
                r'/parents/[0-9]+$',
                r'/seq$',
                r'<^/description$',
                r'/weight$',
                r'/deleted$',
                r'/program/tracking_id$',
                # Descend into nested objects
                r'/[0-9]+$',
                r'/program$',
                r'/survey$',
                r'/survey/structure.*$',
                r'/survey/program$',
            )
            sons = []
            for qm in qnode.qnode_measures:
                measure_respone=self.get_response(qm.measure.id, submission_id)
                measure_responeType=self.get_responseType(qm.measure.response_type_id, program_id)

                ## get submeasures ***************
                submeasureIdList=[]
                for p in measure_responeType.parts:
                    if p.submeasure and (not (p.submeasure in submeasureIdList)):
                       submeasureIdList.append(p.submeasure)

                ## get submeasures ***************   



                mson = to_son(qm.measure)
                mson.update(to_son(qm))
                if len(submeasureIdList) >0:
                   mson['subMeasureList']=self.get_measureList(submeasureIdList, program_id, qnode.survey.id)
                mson['response']=measure_respone
                mson['responseType']=measure_responeType
                mson['parent'] = mson['qnode']
                del mson['qnode']
                if mson['parents'] and len(mson['parents'])>0:
                   mson['parentSeq']=mson['parents'][0].seq+1
                sons.append(mson)
        
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @tornado.web.authenticated
    def post(self, measure_id):
        '''Create new.'''
        if measure_id:
            raise errors.MethodError(
                "Can't specify ID when creating a new measure.")

        program_id = self.get_argument('programId', '')
        parent_id = self.get_argument('parentId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = (
                session.query(model.Program)
                .options(joinedload('surveygroups'))
                .get(program_id))
            if not program:
                raise errors.MissingDocError("No such program")

            if (self.request_son.has_sub_measures==True):
                # create repsone_type for measure
                self.request_son.response_type_id=self.create_response_type(self.request_son.response_type_id, program_id, self.request_son.rt)
                submeasures_list=[]
                merger_parts=[]
                for sm in self.request_son.sub_measures:

                    # create repsone_type for submeasure
                    
                    #sm.response_type_id=self.create_response_type(sm.response_type_id, program_id, sm.rt.definition)
                    sm.response_type_id=self.request_son.response_type_id
                    # create submeasure
                    measure = model.Measure(program=program)
                    session.add(measure)
                    self._update(measure, sm)
                    ##???? get measureId as submeasure
                    session.flush()
                    submeasure_id = str(measure.id)
                     # merge response_type parts
                    # self.request_son.rt.parts.append(self.request_son.rt) 
                    for rt_part in sm.rt.definition.parts:
                        rt_part["submeasure"]=submeasure_id
                        merger_parts.append(rt_part) 
                    submeasures_list.append(submeasure_id)
                    verbs = ['create']
                    if parent_id:
                       verbs.append('relation')
                    act = Activities(session)
                    act.record(user_session.user, measure, verbs)
                    act.ensure_subscription(
                        user_session.user, measure, measure.program, self.reason)

                    log.info("Created submeasure %s", submeasure_id)               
                # create repsone_type
                # self.request_son.rt.parts=[{'submeasure':submeasures_list}]
                # merger_parts.append({'submeasure':submeasures_list})
                self.request_son.rt.parts= merger_parts
                #update response_type's parts which include submeasureId
                self.request_son.response_type_id=self.update_response_type(self.request_son.response_type_id, program_id, self.request_son.rt)
                # create measure
                measure = model.Measure(program=program)
                session.add(measure)
                self._update(measure, self.request_son)
                ## get new measure.id                    
                    ## get new submeasure.id
                    # create measure_measure
            else:
                 measure = model.Measure(program=program)
                 session.add(measure)
                 self._update(measure, self.request_son)

            # Need to flush so object has an ID to record action against.
            session.flush()

            calculator = Calculator.structural()
            if parent_id:
                qnode = (
                    session.query(model.QuestionNode)
                    .get((parent_id, program_id)))
                if not qnode:
                    raise errors.ModelError("No such category")
                qnode_measure = model.QnodeMeasure(
                    program=qnode.program, survey=qnode.survey,
                    qnode=qnode, measure=measure)
                qnode.qnode_measures.reorder()
                self._update_qnode_measure(qnode_measure, self.request_son)
                calculator.mark_measure_dirty(qnode_measure)
                survey = qnode.survey
            else:
                survey = None

            policy = user_session.policy.derive({
                'program': program,
                'survey': survey,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('measure_add')

            calculator.execute()

            measure_id = str(measure.id)

            verbs = ['create']
            if parent_id:
                verbs.append('relation')

            act = Activities(session)
            act.record(user_session.user, measure, verbs)
            act.ensure_subscription(
                user_session.user, measure, measure.program, self.reason)

            log.info("Created measure %s", measure_id)

        self.get(measure_id)

    @tornado.web.authenticated
    def delete(self, measure_id):
        '''Delete an existing measure.'''
        if not measure_id:
            raise errors.MethodError("Measure ID required")

        program_id = self.get_argument('programId', '')
        parent_id = self.get_argument('parentId', '')

        if not parent_id:
            raise errors.ModelError("Please specify a parent to unlink from")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            measure = (
                session.query(model.Measure)
                .get((measure_id, program_id)))
            if not measure:
                raise errors.MissingDocError("No such measure")

            act = Activities(session)

            calculator = Calculator.structural()

            # Just unlink from qnodes
            qnode = (
                session.query(model.QuestionNode)
                .get((parent_id, program_id)))
            if not qnode:
                raise errors.MissingDocError("No such question node")
            qnode_measure = (
                session.query(model.QnodeMeasure)
                .get((program_id, qnode.survey_id, measure.id)))
            if not qnode_measure:
                raise errors.ModelError(
                    "Measure does not belong to that question node")
            calculator.mark_measure_dirty(
                qnode_measure, force_dependants=True)
            qnode.qnode_measures.remove(qnode_measure)
            qnode.qnode_measures.reorder()

            policy = user_session.policy.derive({
                'program': qnode.program,
                'survey': qnode.survey,
                'surveygroups': qnode.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('measure_del')

            calculator.execute()

            act.record(user_session.user, measure, ['delete'])
            act.ensure_subscription(
                user_session.user, measure, measure.program, self.reason)

        self.finish()

    @tornado.web.authenticated
    def put(self, measure_id):
        '''Update existing.'''

        if not measure_id:
            self.ordering()
            return


        program_id = self.get_argument('programId', '')
        survey_id = self.get_argument('surveyId', '')
        parent_id = self.get_argument('parentId', '')



        with model.session_scope() as session:
            user_session = self.get_user_session(session)
            
            # if has sub measure,update response type name first, avoid not to update response type name after submeasure add
            if (self.request_son.has_sub_measures==True):
                self.update_response_type(self.request_son.response_type_id, program_id, self.request_son.rt)  
                session.flush()

            program = (
                session.query(model.Program)
                .options(joinedload('surveygroups'))
                .get(program_id))
            if not program:
                raise errors.MissingDocError("No such program")

            policy = user_session.policy.derive({
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')

            #verbs = set()
            verbs = []
            if (self.request_son.has_sub_measures==True):

                ## get used submeasureIds ***************
                measure_responeType=self.get_responseType(self.request_son.response_type_id, program_id)             
                submeasureIdList=[]
                submeasureIdList.append(measure_id)
                for p in measure_responeType.parts:
                    if p.submeasure and (not (p.submeasure in submeasureIdList)):
                       submeasureIdList.append(p.submeasure)
                ## get used submeasureIds ***************   


            
                submeasures_list=[]
                merger_parts=[]

                for sm in self.request_son.sub_measures:
                    if not sm.deleted:
                        sm.response_type_id=self.request_son.response_type_id
                        if (sm.id and sm.id != 0):
                            subMeasure = (
                              session.query(model.Measure)
                              .get((sm.id, program_id)))
                        else:
                            subMeasure=None      
                        if not subMeasure:
                           # get first unused submeasure
                            subMeasure = (
                                session.query(model.Measure)
                                .filter(model.Measure.response_type_id == self.request_son.response_type_id)
                                .filter(model.Measure.id.notin_(submeasureIdList)).first())

                           # end for get first unused submeasure
                        if not subMeasure:
   
                           # raise errors.MissingDocError("No such measure")

                           # create repsone_type for submeasure

                           #sm.response_type_id=self.create_response_type(sm.response_type_id, program_id, sm.rt.definition)
                           sm.response_type_id=self.request_son.response_type_id
                           ## create submeasure
                           subMeasure = model.Measure(program=program)
                           session.add(subMeasure)
                           self._update(subMeasure, sm)
                           verbs = ['created']
                        else:
                           self._update(subMeasure, sm)
                           verbs = ['updated']
                        ## create repsone_type for submeasure
                    
                        #sm.response_type_id=self.create_response_type(sm.response_type_id, program_id, sm.rt.definition)

                    
                        ###???? get measureId as submeasure
                        session.flush()
                        submeasure_id = str(subMeasure.id)
                        #############
                        #if not (subMeasure.id in submeasureIdList):
                        if not (submeasure_id in submeasureIdList):
                            submeasureIdList.append(submeasure_id)
                        # merge response_type parts
                        # self.request_son.rt.parts.append(self.request_son.rt) 
                        for rt_part in sm.rt.definition.parts:
                            if not "submeasure" in rt_part:
                               rt_part["submeasure"]=submeasure_id
                            merger_parts.append(rt_part) 
                        submeasures_list.append(submeasure_id)
                    
                        ##***** error check later
                        #if parent_id:
                        #   verbs.append('relation')
                        # act = Activities(session)
                        # act.record(user_session.user, subMeasure, verbs)
                        #act.ensure_subscription(
                        #    user_session.user, subMeasure, subMeasure.program, self.reason)
                        ##*****

                        log.info("update/create submeasure %s", submeasure_id) 

                # update response_type
                self.request_son.rt.parts= merger_parts
                withName=False
                self.request_son.response_type_id=self.update_response_type(self.request_son.response_type_id, program_id, self.request_son.rt, withName)           
                ## create repsone_type
                ## self.request_son.rt.parts=[{'submeasure':submeasures_list}]
                ## merger_parts.append({'submeasure':submeasures_list})
                #self.request_son.rt.parts= merger_parts
                #self.request_son.response_type_id=self.create_response_type(self.request_son.response_type_id, program_id, self.request_son.rt)
                ## create measure
                #measure = model.Measure(program=program)
                #session.add(measure)
                #self._update(measure, self.request_son)
                ### get new measure.id                    
                    ## get new submeasure.id
                    # create measure_measure

                # update repsone_type
                # self.request_son.rt.parts=[{'submeasure':submeasures_list}]
                # merger_parts.append({'submeasure':submeasures_list})
            
            


            measure = (
                session.query(model.Measure)
                .get((measure_id, program_id)))
            if not measure:
                raise errors.MissingDocError("No such measure")
          
            #verbs = set()
            
            calculator = Calculator.structural()
            self._update(measure, self.request_son)
            # Check if modified now to avoid problems with autoflush later
            if session.is_modified(measure):
                #verbs.add('update')
                verbs.append('update')
                for qnode_measure in measure.qnode_measures:
                    calculator.mark_measure_dirty(qnode_measure)

            if survey_id:
                qnode_measure = (
                    session.query(model.QnodeMeasure)
                    .get((program_id, survey_id, measure_id)))
                if not qnode_measure:
                    raise errors.MissingDocError(
                        "No such measure in that survey")

                policy = user_session.policy.derive({
                    'program': qnode_measure.program,
                    'survey': qnode_measure.survey,
                })
                policy.verify('measure_edit')
                self._update_qnode_measure(qnode_measure, self.request_son)

                # If relations have changed, mark this measure dirty.
                # No need to check target_vars, because they aren't
                # updated here (that must be done via the other measure).
                if session.is_modified(qnode_measure):
                    verbs.append('update')
                    calculator.mark_measure_dirty(qnode_measure)
                for mv in qnode_measure.source_vars:
                    if session.is_modified(mv):
                        verbs.append('update')
                        calculator.mark_measure_dirty(qnode_measure)

            def relink(new_parent):
                # Add links to parents. Links can't be removed like this;
                # use the delete method instead.
                qnode_measure = measure.get_qnode_measure(new_parent.survey_id)
                if qnode_measure:
                    old_parent = qnode_measure.qnode
                    if old_parent == new_parent:
                        return False
                    # Mark dirty now, before the move, to cause old parents
                    # to be updated.
                    calculator.mark_measure_dirty(qnode_measure)
                    self.reason(
                        'Moved from %s to %s' %
                        (old_parent.get_path(), new_parent.get_path()))
                    qnode_measure.qnode = new_parent
                    old_parent.qnode_measures.reorder()
                else:
                    qnode_measure = model.QnodeMeasure(
                        program=new_parent.program,
                        survey=new_parent.survey,
                        qnode=new_parent, measure=measure)
                    self.reason('Added to %s' % new_parent.get_path())
                new_parent.qnode_measures.reorder()
                # Mark dirty again.
                calculator.mark_measure_dirty(
                    qnode_measure, force_dependants=True)
                return True

            if parent_id:
                new_parent = (
                    session.query(model.QuestionNode)
                    .get((parent_id, program_id)))
                if not new_parent:
                    raise errors.ModelError("No such category")
                policy = user_session.policy.derive({
                    'program': new_parent.program,
                    'survey': new_parent.survey,
                })
                policy.verify('measure_edit')
                if relink(new_parent):
                    verbs.append('relation')

            calculator.execute()
            ## error check later
            ##act = Activities(session)
            ##act.record(user_session.user, measure, verbs)
            ##act.ensure_subscription(
            ##    user_session.user, measure, measure.program, self.reason)
            ##***** 

        self.get(measure_id)

    def ordering(self):
        '''Change the order that would be returned by a query.'''

        program_id = self.get_argument('programId', '')
        qnode_id = self.get_argument('qnodeId', '')
        if qnode_id == None:
            raise errors.MethodError("Question node ID is required.")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)
            qnode = (
                session.query(model.QuestionNode)
                .get((qnode_id, program_id)))
            policy = user_session.policy.derive({
                'program': qnode.program,
                'survey': qnode.survey,
                'surveygroups': qnode.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('measure_edit')
            reorder(
                qnode.qnode_measures, self.request_son,
                id_attr='measure_id')

            act = Activities(session)
            act.record(user_session.user, qnode, ['reorder_children'])
            act.ensure_subscription(
                user_session.user, qnode, qnode.program, self.reason)

        self.query()

    def _update(self, measure, son):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(measure, error_factory=errors.ModelError)
        update('title', son)
        update('weight', son)
        update('response_type_id', son)
        update('description', son)
        # update('description', son, sanitise=True)
        # update('has_sub_measures', son)

    def _update_qnode_measure(self, qnode_measure, son):
        if 'source_vars' in son:
            source_var_map = {
                mv.target_field: mv
                for mv in qnode_measure.source_vars}

            source_vars = []
            for mv_son in son['source_vars']:
                if not mv_son.get('source_measure'):
                    continue
                if not mv_son.get('source_field'):
                    continue
                k = mv_son['target_field']
                mv = source_var_map.get(k)
                if mv is None:
                    mv = model.MeasureVariable(
                        program=qnode_measure.program,
                        survey=qnode_measure.survey,
                        target_qnode_measure=qnode_measure,
                        target_field=mv_son['target_field'])
                sm = mv_son.get('source_measure')
                mv.source_measure_id = sm and sm.get('id') or None
                mv.source_field = mv_son.get('source_field') or None
                source_vars.append(mv)
            qnode_measure.source_vars = source_vars

    ## 

    def get_response(self, measure_id, submission_id):
        '''Get a single response.'''

        if not measure_id:
            # self.query(submission_id)
            return

        version = self.get_argument('version', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            response = (
                session.query(model.Response)
                .get((submission_id, measure_id)))

            if response:
                submission = response.submission
                dummy = False
            else:
                # Synthesise response so it can be returned. The session will
                # be rolled back to avoid actually making this change.
                submission = (
                    session.query(model.Submission)
                    .get(submission_id))
                if not submission:
                    raise errors.MissingDocError("No such submission")

                qnode_measure = (
                    session.query(model.QnodeMeasure)
                    .get((
                        submission.program_id, submission.survey_id,
                        measure_id)))
                if not qnode_measure:
                    raise errors.MissingDocError(
                        "That survey has no such measure")

                response = model.Response(
                    qnode_measure=qnode_measure,
                    submission=submission,
                    user_id=user_session.user.id,
                    comment='',
                    response_parts=[],
                    variables={},
                    not_relevant=False,
                    approval='draft',
                    modified=datetime.datetime.fromtimestamp(0),
                )
                dummy = True

            response_history = self.get_version(session, response, version)

            policy = user_session.policy.derive({
                'org': submission.organisation,
                'submission': submission,
                'surveygroups': submission.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('response_view')

            to_son = ToSon(
                # Fields to match from any visited object
                r'/ob_type$',
                r'/id$',
                r'/title$',
                r'/name$',
                # Fields to match from only the root object
                r'^/submission_id$',
                r'^/measure_id$',
                r'<^/comment$',
                r'^/response_parts.*$',
                r'^/not_relevant$',
                r'^/attachments$',
                r'^/audit_reason$',
                r'^/error$',
                r'^/approval$',
                r'^/version$',
                r'^/modified$',
                r'^/latest_modified$',
                r'^/quality$',
                # Descend
                r'/parent$',
                r'/measure$',
                r'/submission$',
                r'/user$',
            )

            if dummy:
                to_son.add(r'!/user$')

            to_son.exclude(
                # The IDs of rnodes and responses are not part of the API
                r'^/id$',
                r'/parent/id$'
            )
            if response_history is None:
                son = to_son(response)
            else:
                son = to_son(response_history)
                submission = (
                    session.query(model.Submission)
                    .filter_by(id=response_history.submission_id)
                    .first())
                measure = (
                    session.query(model.Measure)
                    .filter_by(id=response_history.measure_id,
                               program_id=submission.program_id)
                    .first())
                qnode_measure = measure.get_qnode_measure(submission.survey_id)
                parent = model.ResponseNode.from_qnode(
                    qnode_measure.qnode, submission)
                user = (session.query(model.AppUser)
                        .filter_by(id=response_history.user_id)
                        .first())
                dummy_relations = {
                    'parent': parent,
                    'measure': measure,
                    'submission': submission,
                    'user': user,
                }
                son.update(to_son(dummy_relations))

            # Always include the mtime of the most recent version. This is used
            # to avoid edit conflicts.
            dummy_relations = {
                'latest_modified': response.modified,
            }
            son.update(to_son(dummy_relations))

            def gather_variables(response):
                source_responses = {
                    mv.source_qnode_measure: model.Response.from_measure(
                        mv.source_qnode_measure, response.submission)
                    for mv in response.qnode_measure.source_vars}
                source_variables = {
                    source_qnode_measure: response and response.variables or {}
                    for source_qnode_measure, response
                    in source_responses.items()}
                variables_by_target = {
                    mv.target_field:
                    source_variables[mv.source_qnode_measure].get(
                        mv.source_field)
                    for mv in response.qnode_measure.source_vars}
                # Filter out blank/null variables
                return {k: v for k, v in variables_by_target.items() if v}
            son['sourceVars'] = gather_variables(response)

            # Explicit rollback to avoid committing dummy response.
            session.rollback()
        return son
        ## self.set_header("Content-Type", "application/json")
        ## self.write(json_encode(son))
        ## self.finish()

    def get_version(self, session, response, version):
        if not version:
            return None

        try:
            version = int(version)
        except ValueError:
            raise errors.ModelError("Invalid version number")
        if version == response.version:
            return None

        history = (
            session.query(model.ResponseHistory)
            .get((response.submission_id, response.measure_id, version)))

        if history is None:
            raise errors.MissingDocError("No such version")
        return history

    def get_responseType(self, response_type_id, program_id):
        '''Get single response type'''
        if not response_type_id:
            self.query()
            return

        # program_id = self.get_argument('programId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            response_type, count = (
                session.query(model.ResponseType, func.count(model.Measure.id))
                .outerjoin(model.Measure)
                .join(model.QnodeMeasure)
                .filter(model.Measure.id == model.QnodeMeasure.measure_id)
                .filter(model.ResponseType.id == response_type_id)
                .filter(model.ResponseType.program_id == program_id)
                .group_by(model.ResponseType.id, model.ResponseType.program_id)
                .first()) or (None, None)
            if not response_type:
                raise errors.MissingDocError("No such response type")

            policy = user_session.policy.derive({
                'program': response_type.program,
                'surveygroups': response_type.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('response_type_view')

            to_son = ToSon(
                r'/id$',
                r'/program_id$',
                r'/ob_type$',
                r'/name$',
                r'/title$',
                r'/parts$',
                r'/parts/.*',
                r'/formula$',
                r'/n_measures$',
                r'/program$',
                omit=True)
            son = to_son(response_type)
            if response_type.parts and 'submeasure' in response_type.parts[0]:
                count=1   
                    #sid=None                   
                    #for p in response_type.parts:
                    #    if p['submeasure'] != sid:
                    #       submeasures.append({
                    #           'id': p['submeasure'],
                    #           'parts':[p]
                    #        })
                    #    else:
                    #       submeasures[len(submeasures)-1]['parts'].append(p)
                    #    sid=p['submeasure']
                     
            son['nMeasures'] = count
        return son

    def get_measure(self, measure_id, submission_id, program_id, survey_id ):
        if not measure_id:
        ## self.query()
           return

        '''Get a single measure.'''
        # program_id = self.get_argument('programId', '')
        # survey_id = self.get_argument('surveyId', '')
        if not program_id:
            raise errors.MissingDocError("Missing program ID")

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = (
                session.query(model.Program)
                .options(joinedload('surveygroups'))
                .get(program_id))
            if not program:
                raise errors.MissingDocError("No such program")

            if survey_id:
                survey = session.query(model.Survey).get(
                    (survey_id, program_id))
            else:
                survey = None

            query = (
                session.query(model.Measure)
                .filter(model.Measure.id == measure_id)
                .filter(model.Measure.program_id == program_id))
            if survey_id:
                query = (
                    query
                    .join(model.QnodeMeasure)
                    .filter(model.QnodeMeasure.survey_id == survey_id))

            measure = query.first()
            if not measure:
                raise errors.MissingDocError("No such measure")

            policy = user_session.policy.derive({
                'program': program,
                'survey': survey,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('measure_view')

            to_son = ToSon(
                # Fields to match from any visited object
                r'/ob_type$',
                r'/id$',
                r'/title$',
                r'/seq$',
                r'/deleted$',
                r'/program_id$',
                r'/program/tracking_id$',
                r'/program/created$',
                r'<^/description$',
                r'^/weight$',
                r'^/response_type_id$',
                r'/parent$',
                r'/parents$',
                r'/parents/[0-9]+$',
                r'/survey$',
                r'/survey/program$',
                r'/survey/structure.*$',
                r'/has_quality$',
                r'/is_editable$',
            )
            son = to_son(measure)

            if survey_id:
                qnode_measure = measure.get_qnode_measure(survey_id)

                to_son = ToSon(
                    r'/id$',
                    r'/ob_type$',
                    r'/seq$',
                    r'/title$',
                    r'^/error$',
                    r'/qnode$',
                    r'/parent$',
                    r'/deleted$',
                    r'/survey$',
                    r'/survey/program$',
                    r'/is_editable$',
                    r'/survey/structure.*$',
                    r'/survey/program_id$',
                    r'/survey/program/tracking_id$',
                    r'/survey/program/created$',
                    r'/has_quality$',
                )
                son.update(to_son(qnode_measure))
                son['parent'] = son['qnode']
                del son['qnode']

                # Variables, handled separately to avoid excessive recursion
                to_son = ToSon()
                son['sourceVars'] = to_son([{
                    'source_measure': {
                        'id': mv.source_qnode_measure.measure_id,
                        'title': mv.source_qnode_measure.measure.title,
                        'declared_vars': self.get_declared_vars(
                            mv.source_qnode_measure.measure)
                    },
                    'source_field': mv.source_field,
                    'target_field': mv.target_field,
                } for mv in qnode_measure.source_vars])
                son['targetVars'] = to_son([{
                    'target_measure': {
                        'id': mv.target_qnode_measure.measure_id,
                        'title': mv.target_qnode_measure.measure.title,
                    },
                    'source_field': mv.source_field,
                    'target_field': mv.target_field,
                } for mv in qnode_measure.target_vars])

                QnodeMeasure = model.QnodeMeasure
                prev = (
                    session.query(QnodeMeasure)
                    .filter(QnodeMeasure.qnode_id == qnode_measure.qnode_id,
                            QnodeMeasure.program_id == measure.program_id,
                            QnodeMeasure.seq < son['seq'])
                    .order_by(QnodeMeasure.seq.desc())
                    .first())
                next_ = (
                    session.query(QnodeMeasure)
                    .filter(QnodeMeasure.qnode_id == qnode_measure.qnode_id,
                            QnodeMeasure.program_id == measure.program_id,
                            QnodeMeasure.seq > son['seq'])
                    .order_by(QnodeMeasure.seq)
                    .first())

                if prev is not None:
                    son['prev'] = str(prev.measure_id)
                if next_ is not None:
                    son['next'] = str(next_.measure_id)

            else:
                son['program'] = to_son(measure.program) 
        return son

    def get_measureList(self, measureIds, program_id, survey_id):
        '''Get a list.'''
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = (
                session.query(model.Program)
                .options(joinedload('surveygroups'))
                .get(program_id))
            if not program:
                raise errors.MissingDocError("No such program")

            if survey_id:
                survey = (
                    session.query(model.Survey).get([survey_id, program_id]))
            else:
                survey = None

            policy = user_session.policy.derive({
                'survey': survey,
                'program': program,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('measure_view')

            query = (
                session.query(model.Measure)
                     .filter(model.Measure.program_id == program_id)
                     .filter(model.Measure.id.in_(measureIds)))   
            measures = query.all()
            to_son = ToSon(
                r'/id$',
                r'/title$',
                r'/description$',
                r'/program_id$',
            )
            sons=[]
            for s in measures:
                mson = to_son(s)
                sons.append(mson)

        return sons


    def create_response_type(self, response_type_id, program_id, rt_son):
        '''Create new'''
        if response_type_id:
            raise errors.ModelError("Can't specify ID when creating")

        # program_id = self.get_argument('programId', '')

        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            program = session.query(model.Program).get(program_id)
            if not program:
                raise errors.MissingDocError("No such program")

            policy = user_session.policy.derive({
                'program': program,
                'surveygroups': program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('response_type_add')
            
            if rt_son.name:
                rt_by_name = (
                   session.query(model.ResponseType)
                   .filter(model.ResponseType.program_id == program_id)
                   .filter(model.ResponseType.name == rt_son.name)
                   .first())
                if rt_by_name:
                   raise errors.ModelError(
                      "'"+rt_son.name + "' as a response type of that name already exists")

            response_type = model.ResponseType(program=program)
            session.add(response_type)
            try:
                self._update_response_type(response_type, rt_son)
            except ResponseTypeError as e:
                raise errors.ModelError(str(e))
            except voluptuous.error.Error as e:
                raise errors.ModelError(str(e))
            except Exception as e:
                raise errors.ModelError(str(e))

            try:
                session.flush()
            except sqlalchemy.exc.IntegrityError as e:
                raise errors.ModelError.from_sa(e)

            response_type_id = str(response_type.id)
            # No need for survey update: RT is not being used yet

            act = Activities(session)
            act.record(user_session.user, response_type, ['create'])
            act.ensure_subscription(
                user_session.user, response_type, response_type.program,
                self.reason)
        #self.get(response_type_id)
        return response_type_id

    def update_response_type(self, response_type_id, program_id, rt_son, withName=True):
        '''Create new'''
        #if response_type_id:
        #    raise errors.ModelError("Can't specify ID when creating")

        # program_id = self.get_argument('programId', '')
        with model.session_scope() as session:
            user_session = self.get_user_session(session)

            response_type = (
                session.query(model.ResponseType)
                .get((response_type_id, program_id)))
            if not response_type:
                raise errors.MissingDocError("No such response type")

            policy = user_session.policy.derive({
                'program': response_type.program,
                'surveygroups': response_type.program.surveygroups,
            })
            policy.verify('surveygroup_interact')
            policy.verify('response_type_edit')

            if 'name' in rt_son:
                rt_by_name = (
                    session.query(model.ResponseType)
                    .filter(model.ResponseType.program_id == program_id)
                    .filter(model.ResponseType.name == rt_son.name)
                    .first())
                if rt_by_name and rt_by_name != response_type:
                    raise errors.ModelError(
                        "'"+rt_son.name + "' as a response type of that name already exists")

            try:
                self._update_response_type(response_type, rt_son, withName)
            except ResponseTypeError as e:
                raise errors.ModelError(str(e))
            except voluptuous.error.Error as e:
                raise errors.ModelError(str(e))
            except Exception as e:
                raise errors.ModelError(str(e))

            verbs = []
            # Check if modified now to avoid problems with autoflush later
            if session.is_modified(response_type):
                verbs.append('update')
                calculator = Calculator.structural()
                for measure in response_type.measures:
                    for qnode_measure in measure.qnode_measures:
                        calculator.mark_measure_dirty(qnode_measure)
                calculator.execute()

            act = Activities(session)
            act.record(user_session.user, response_type, verbs)
            act.ensure_subscription(
                user_session.user, response_type, response_type.program,
                self.reason)
        #self.get(response_type_id)
        return response_type_id

  
    def _update_response_type(self, response_type, son, withName=True):
        '''Apply user-provided data to the saved model.'''
        update = updater(response_type, error_factory=errors.ModelError)
        if withName:
           update('name', son)
        update('parts', son)
        update('formula', son)
