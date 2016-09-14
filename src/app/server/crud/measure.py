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
        parent_id = self.get_argument('parentId', '')
        submission_id = self.get_argument('submissionId', '')

        with model.session_scope() as session:
            if submission_id:
                submission = session.query(model.Submission).get(submission_id)
                if not submission:
                    raise handlers.MissingDocError("No such submission")
                program_id = submission.program_id
                survey_id = submission.survey_id
                parent = None
            elif parent_id:
                program_id = self.program_id
                parent = (session.query(model.QuestionNode)
                    .get((parent_id, program_id)))
                if not parent:
                     raise handlers.MissingDocError("No such category")
                survey_id = parent.survey_id
            else:
                program_id = self.program_id
                parent = None
                survey_id = None

            self.check_browse_program(session, program_id, survey_id)

            try:
                measure = session.query(model.Measure)\
                    .get((measure_id, program_id))
                if measure is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such measure")

            to_son = ToSon(
                # Fields to match from any visited object
                r'/ob_type$',
                r'/id$',
                r'/title$',
                r'/seq$',
                r'/deleted$',
                r'/is_editable$',
                r'/program_id$',
                r'/program/tracking_id$',
                r'/program/created$',
                # Fields to match from only the root object
                r'<^/description$',
                r'^/weight$',
                r'^/response_type_id$',
                # Descend into nested objects
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
                if not qnode_measure:
                     raise handlers.MissingDocError(
                         "This measure does not belong to that survey")
                parent = qnode_measure.qnode

                son['parent'] = to_son(parent)
                son['seq'] = qnode_measure.seq
                prev = (session.query(model.QnodeMeasure)
                    .filter(model.QnodeMeasure.qnode_id == parent.id,
                            model.QnodeMeasure.program_id == measure.program_id,
                            model.QnodeMeasure.seq < son['seq'])
                    .order_by(model.QnodeMeasure.seq.desc())
                    .first())
                next_ = (session.query(model.QnodeMeasure)
                    .filter(model.QnodeMeasure.qnode_id == parent.id,
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

        with model.session_scope() as session:
            if orphan != '' and truthy(orphan):
                # Orphans only
                query = session.query(model.Measure)\
                    .outerjoin(model.QnodeMeasure)\
                    .filter(model.Measure.program_id == self.program_id)\
                    .filter(model.QnodeMeasure.qnode_id == None)
            elif orphan != '' and falsy(orphan):
                # Non-orphans only
                query = session.query(model.Measure)\
                    .join(model.QnodeMeasure)\
                    .filter(model.Measure.program_id == self.program_id)
            else:
                # All measures
                query = session.query(model.Measure)\
                    .filter_by(program_id=self.program_id)

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

            query = self.paginate(query)

            measures = query.all()

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
            sons = to_son(measures)

            for mson, measure in zip(sons, measures):
                mson['orphan'] = len(measure.qnode_measures) == 0

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    def query_children_of(self, qnode_id):
        with model.session_scope() as session:
            # Only children of a certain qnode
            qnode = session.query(model.QuestionNode)\
                .get((qnode_id, self.program_id))

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

        parent_ids = [p for p in self.get_arguments('parentId')
                      if p != '']

        try:
            with model.session_scope() as session:
                measure = model.Measure(program_id=self.program_id)
                session.add(measure)
                self._update(measure, self.request_son)

                # Need to flush so object has an ID to record action against.
                session.flush()

                calculator = Calculator.structural()
                for parent_id in parent_ids:
                    qnode = session.query(model.QuestionNode)\
                        .get((parent_id, self.program_id))
                    if qnode is None:
                        raise handlers.ModelError("No such question node")
                    qnode_measure = model.QnodeMeasure(
                        program=qnode.program, survey=qnode.survey,
                        qnode=qnode, measure=measure)
                    qnode.qnode_measures.reorder()
                    calculator.mark_measure_dirty(qnode_measure)

                calculator.execute()

                measure_id = str(measure.id)

                verbs = ['create']
                if len(parent_ids) > 0:
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

        parent_ids = [p for p in self.get_arguments('parentId')
                      if p != '']

        if len(parent_ids) == 0:
            raise handlers.ModelError("Please specify a parent to unlink from")

        self.check_editable()

        try:
            with model.session_scope() as session:
                measure = session.query(model.Measure)\
                    .get((measure_id, self.program_id))
                if measure is None:
                    raise handlers.MissingDocError("No such measure")

                act = Activities(session)

                calculator = Calculator.structural()

                # Just unlink from qnodes
                for parent_id in parent_ids:
                    qnode = (session.query(model.QuestionNode)
                        .get((parent_id, self.program_id)))
                    if qnode is None:
                        raise handlers.MissingDocError(
                            "No such question node")
                    qnode_measure = (session.query(model.QnodeMeasure)
                        .get((self.program_id, qnode.survey_id, measure.id)))
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

        parent_ids = [p for p in self.get_arguments('parentId')
                      if p != '']

        try:
            with model.session_scope() as session:
                measure = session.query(model.Measure)\
                    .get((measure_id, self.program_id))
                if measure is None:
                    raise handlers.MissingDocError("No such measure")
                self._update(measure, self.request_son)

                verbs = []
                # Check if modified now to avoid problems with autoflush later
                calculator = Calculator.structural()
                if session.is_modified(measure):
                    verbs.append('update')
                    for qnode_measure in measure.qnode_measures:
                        calculator.mark_measure_dirty(qnode_measure)

                has_relocated = False
                for parent_id in parent_ids:
                    # Add links to parents. Links can't be removed like this;
                    # use the delete method instead.
                    new_parent = session.query(model.QuestionNode)\
                        .get((parent_id, self.program_id))
                    if new_parent is None:
                        raise handlers.ModelError("No such question node")
                    qnode_measure = measure.get_qnode_measure(new_parent.survey_id)
                    if qnode_measure:
                        old_parent = qnode_measure.qnode
                        if old_parent == new_parent:
                            continue
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
                    has_relocated = True
                    new_parent.qnode_measures.reorder()
                    # Mark dirty again.
                    calculator.mark_measure_dirty(
                        qnode_measure, force_dependants=True)

                if has_relocated:
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

        qnode_id = self.get_argument('qnodeId', '')
        if qnode_id == None:
            raise handlers.MethodError("Question node ID is required.")

        list
        try:
            with model.session_scope() as session:
                qnode = session.query(model.QuestionNode)\
                    .get((qnode_id, self.program_id))
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
        update('description', son, sanitise=True)
