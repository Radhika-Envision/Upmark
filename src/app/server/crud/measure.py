from collections import defaultdict
import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy import cast, String
from sqlalchemy.orm import joinedload

from activity import Activities
import crud
import handlers
import logging
import model
from score import Calculator
from utils import falsy, reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.measure')


class MeasureHandler(
        handlers.Paginate,
        crud.program.ProgramCentric, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, measure_id):
        if measure_id == '':
            self.query()
            return

        '''Get a single measure.'''
        program_id = self.get_argument('programId', '')
        submission_id = self.get_argument('submissionId', '')
        survey_id = self.get_argument('surveyId', '')

        with model.session_scope() as session:
            if submission_id:
                submission = session.query(model.Submission).get(submission_id)
                if not submission:
                    raise handlers.MissingDocError("No such submission")
                program_id = submission.program_id
                survey_id = submission.survey_id

            self.check_browse_program(session, program_id, survey_id)

            query = (session.query(model.Measure)
                .filter(model.Measure.id == measure_id)
                .filter(model.Measure.program_id == program_id))
            if survey_id:
                query = (query
                    .join(model.QnodeMeasure)
                    .filter(model.QnodeMeasure.survey_id == survey_id))

            measure = query.first()
            if not measure:
                raise handlers.MissingDocError("No such measure")

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
                r'/survey$',
                r'/survey/program$',
                r'/survey/structure.*$',
                r'/has_quality$',
            )
            if not submission_id:
                to_son.add(
                    r'/parents$',
                    r'/parents/[0-9]+$',
                )
            son = to_son(measure)

            if survey_id:
                qnode_measure = measure.get_qnode_measure(survey_id)

                to_son = ToSon(
                    r'/id$',
                    r'/ob_type$',
                    r'/seq$',
                    r'/title$',
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

                prev = (session.query(model.QnodeMeasure)
                    .filter(model.QnodeMeasure.qnode_id == qnode_measure.qnode_id,
                            model.QnodeMeasure.program_id == measure.program_id,
                            model.QnodeMeasure.seq < son['seq'])
                    .order_by(model.QnodeMeasure.seq.desc())
                    .first())
                next_ = (session.query(model.QnodeMeasure)
                    .filter(model.QnodeMeasure.qnode_id == qnode_measure.qnode_id,
                            model.QnodeMeasure.program_id == measure.program_id,
                            model.QnodeMeasure.seq > son['seq'])
                    .order_by(model.QnodeMeasure.seq)
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
        if qnode_id != '':
            self.query_children_of(qnode_id)
            return;

        orphan = self.get_argument('orphan', '')
        term = self.get_argument('term', '')
        program_id = self.get_argument('programId', '')
        survey_id = self.get_argument('surveyId', '')

        to_son = ToSon(
            # Fields to match from any visited object
            r'/id$',
            r'/title$',
            r'<^/description$',
            r'/seq$',
            r'/weight$',
            r'/deleted$',
            r'/program/tracking_id$',
            # Descend into nested objects
            r'/[0-9]+$',
            r'/program$',
        )

        with model.session_scope() as session:
            if orphan != '' and truthy(orphan):
                # Orphans only
                query = session.query(model.Measure)\
                    .outerjoin(model.QnodeMeasure)\
                    .filter(model.Measure.program_id == program_id)\
                    .filter(model.QnodeMeasure.qnode_id == None)
            elif orphan != '' and falsy(orphan):
                # Non-orphans only
                query = session.query(model.Measure)\
                    .join(model.QnodeMeasure)\
                    .filter(model.Measure.program_id == program_id)
            else:
                # All measures
                query = session.query(model.Measure)\
                    .filter_by(program_id=program_id)

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
                query = (query
                    .join(model.ResponseType)
                    .filter(
                        (cast(model.ResponseType.id, String) == rt_term) |
                        (model.ResponseType.name.ilike(r'%{}%'.format(rt_term)))
                    ))

            if truthy(self.get_argument('withResponseTypes', '')):
                query = (query.options(joinedload('response_type')))
                to_son.add(
                    r'/response_type$',
                    r'/response_type/id$',
                    r'/response_type/name$',
                    r'/response_type/parts.*$',
                    r'/response_type/formula$',
                    r'!/response_type/program$',
                )

            if survey_id:
                query = (query
                    .join(model.QnodeMeasure)
                    .filter(model.QnodeMeasure.survey_id == survey_id))

            query = self.paginate(query)

            measures = query.all()
            sons = to_son(measures)

            for mson, measure in zip(sons, measures):
                mson['orphan'] = len(measure.qnode_measures) == 0

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    def query_children_of(self, qnode_id):
        program_id = self.get_argument('programId', '')
        with model.session_scope() as session:
            # Only children of a certain qnode
            qnode = session.query(model.QuestionNode)\
                .get((qnode_id, program_id))

            to_son = ToSon(
                # Fields to match from any visited object
                r'/id$',
                r'/title$',
                r'/seq$',
                r'/weight$',
                r'/deleted$',
                r'/program/tracking_id$',
                # Descend into nested objects
                r'/[0-9]+$',
                r'/program$',
            )
            sons = []
            for qm in qnode.qnode_measures:
                mson = to_son(qm.measure)
                mson.update(to_son(qm))
                sons.append(mson)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('author')
    def post(self, measure_id):
        '''Create new.'''
        if measure_id != '':
            raise handlers.MethodError(
                "Can't specify ID when creating a new measure.")

        self.check_editable()

        program_id = self.get_argument('programId', '')
        survey_id = self.get_argument('surveyId', '')
        parent_id = self.get_argument('parentId', '')

        try:
            with model.session_scope() as session:
                measure = model.Measure(program_id=program_id)
                session.add(measure)
                self._update(measure, self.request_son)

                # Need to flush so object has an ID to record action against.
                session.flush()

                calculator = Calculator.structural()
                if parent_id:
                    qnode = session.query(model.QuestionNode)\
                        .get((parent_id, program_id))
                    if qnode is None:
                        raise handlers.ModelError("No such question node")
                    qnode_measure = model.QnodeMeasure(
                        program=qnode.program, survey=qnode.survey,
                        qnode=qnode, measure=measure)
                    qnode.qnode_measures.reorder()
                    self._update_qnode_measure(qnode_measure, self.request_son)
                    calculator.mark_measure_dirty(qnode_measure)

                calculator.execute()

                measure_id = str(measure.id)

                verbs = ['create']
                if parent_id:
                    verbs.append('relation')

                act = Activities(session)
                act.record(self.current_user, measure, verbs)
                if not act.has_subscription(self.current_user, measure):
                    act.subscribe(self.current_user, measure.program)
                    self.reason("Subscribed to program")

                log.info("Created measure %s", measure_id)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(measure_id)

    @handlers.authz('author')
    def delete(self, measure_id):
        '''Delete an existing measure.'''
        if measure_id == '':
            raise handlers.MethodError("Measure ID required")

        program_id = self.get_argument('programId', '')
        parent_id = self.get_argument('parentId', '')

        if not parent_id:
            raise handlers.ModelError("Please specify a parent to unlink from")

        self.check_editable()

        try:
            with model.session_scope() as session:
                measure = session.query(model.Measure)\
                    .get((measure_id, program_id))
                if measure is None:
                    raise handlers.MissingDocError("No such measure")

                act = Activities(session)

                calculator = Calculator.structural()

                # Just unlink from qnodes
                if parent_id:
                    qnode = (session.query(model.QuestionNode)
                        .get((parent_id, program_id)))
                    if qnode is None:
                        raise handlers.MissingDocError(
                            "No such question node")
                    qnode_measure = (session.query(model.QnodeMeasure)
                        .get((program_id, qnode.survey_id, measure.id)))
                    if qnode_measure is None:
                        raise handlers.ModelError(
                            "Measure does not belong to that question node")
                    calculator.mark_measure_dirty(
                        qnode_measure, force_dependants=True)
                    qnode.qnode_measures.remove(qnode_measure)
                    qnode.qnode_measures.reorder()

                calculator.execute()

                act.record(self.current_user, measure, ['delete'])
                if not act.has_subscription(self.current_user, measure):
                    act.subscribe(self.current_user, measure.program)
                    self.reason("Subscribed to program")

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError("Measure is in use")
        except sqlalchemy.exc.StatementError:
            raise handlers.MissingDocError("No such measure")

        self.finish()

    @handlers.authz('author')
    def put(self, measure_id):
        '''Update existing.'''

        self.check_editable()

        if measure_id == '':
            self.ordering()
            return

        program_id = self.get_argument('programId', '')
        survey_id = self.get_argument('surveyId', '')
        parent_id = self.get_argument('parentId', '')

        try:
            with model.session_scope() as session:
                measure = session.query(model.Measure)\
                    .get((measure_id, program_id))
                if measure is None:
                    raise handlers.MissingDocError("No such measure")

                verbs = []
                calculator = Calculator.structural()
                self._update(measure, self.request_son)
                # Check if modified now to avoid problems with autoflush later
                if session.is_modified(measure):
                    verbs.append('update')
                    for qnode_measure in measure.qnode_measures:
                        calculator.mark_measure_dirty(qnode_measure)

                if survey_id:
                    qnode_measure = (session.query(model.QnodeMeasure)
                        .get((program_id, survey_id, measure_id)))
                    if not qnode_measure:
                        raise handlers.MissingDocError("No such measure in that survey")
                    self._update_qnode_measure(qnode_measure, self.request_son)

                    if session.is_modified(qnode_measure):
                        if not 'update' in verbs:
                            verbs.append('update')
                        calculator.mark_measure_dirty(qnode_measure)

                def relink(parent_id):
                    # Add links to parents. Links can't be removed like this;
                    # use the delete method instead.
                    new_parent = session.query(model.QuestionNode)\
                        .get((parent_id, program_id))
                    if new_parent is None:
                        raise handlers.ModelError("No such question node")
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
                            program=new_parent.program, survey=new_parent.survey,
                            qnode=new_parent, measure=measure)
                        self.reason('Added to %s' % new_parent.get_path())
                    new_parent.qnode_measures.reorder()
                    # Mark dirty again.
                    calculator.mark_measure_dirty(
                        qnode_measure, force_dependants=True)
                    return True

                if parent_id:
                    if relink(parent_id):
                        verbs.append('relation')

                calculator.execute()

                act = Activities(session)
                act.record(self.current_user, measure, verbs)
                if not act.has_subscription(self.current_user, measure):
                    act.subscribe(self.current_user, measure.program)
                    self.reason("Subscribed to program")

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(measure_id)

    def ordering(self):
        '''Change the order that would be returned by a query.'''

        self.check_editable()

        program_id = self.get_argument('programId', '')
        qnode_id = self.get_argument('qnodeId', '')
        if qnode_id == None:
            raise handlers.MethodError("Question node ID is required.")

        list
        try:
            with model.session_scope() as session:
                qnode = session.query(model.QuestionNode)\
                    .get((qnode_id, program_id))
                reorder(
                    qnode.qnode_measures, self.request_son,
                    id_attr='measure_id')

                act = Activities(session)
                act.record(self.current_user, qnode, ['reorder_children'])
                if not act.has_subscription(self.current_user, qnode):
                    act.subscribe(self.current_user, qnode.program)
                    self.reason("Subscribed to program")

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)

        self.query()

    def _update(self, measure, son):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(measure)
        update('title', son)
        update('weight', son)
        update('response_type_id', son)
        update('description', son, sanitise=True)

    def _update_qnode_measure(self, qnode_measure, son):
        if 'source_vars' in son:
            source_var_map = {
                mv.target_field: mv
                for mv in qnode_measure.source_vars}

            source_vars = []
            for mv_son in son['source_vars']:
                k = mv_son['target_field']
                mv = source_var_map.get(k)
                if mv is None:
                    mv = model.MeasureVariable(
                        program=qnode_measure.program,
                        survey=qnode_measure.survey,
                        target_qnode_measure=qnode_measure,
                        target_field=mv_son['target_field'])
                mv.source_measure_id = mv_son['source_measure']['id']
                mv.source_field = mv_son['source_field']
                source_vars.append(mv)
            qnode_measure.source_vars = source_vars
