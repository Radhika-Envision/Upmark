import datetime
import time
import uuid

from tornado.escape import json_decode, json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.orm import joinedload

import handlers
import model
import logging

import crud
from utils import falsy, reorder, ToSon, truthy, updater


log = logging.getLogger('app.crud.measure')


class MeasureHandler(
        handlers.Paginate,
        crud.survey.SurveyCentric, handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, measure_id):
        '''Get a single measure.'''

        if measure_id == '':
            self.query()
            return

        parent_id = self.get_argument('parentId', '')

        with model.session_scope() as session:
            try:
                measure = session.query(model.Measure)\
                    .get((measure_id, self.survey_id))
                if measure is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError,
                    sqlalchemy.orm.exc.NoResultFound,
                    ValueError):
                raise handlers.MissingDocError("No such measure")

            to_son = ToSon(include=[
                # Fields to match from any visited object
                r'/id$',
                r'/title$',
                r'/seq$',
                r'/is_editable$',
                r'/survey/tracking_id$',
                r'/survey/created$',
                # Fields to match from only the root object
                r'^/intent$',
                r'^/inputs$',
                r'^/scenario$',
                r'^/questions$',
                r'^/weight$',
                r'^/response_type$',
                # Descend into nested objects
                r'/parents$',
                r'/parents/[0-9]+$',
                r'/parent$',
                r'/hierarchy$',
                r'/hierarchy/survey$',
                r'/hierarchy/structure.*$',
                r'/response_types.*$'
            ])
            son = to_son(measure)

            if parent_id != '':
                for p, link in zip(son['parents'], measure.qnode_measures):
                    if str(link.qnode_id) == parent_id:
                        son['parent'] = p
                        son['seq'] = link.seq
                        break
                if 'parent' not in son:
                    raise handlers.MissingDocError(
                        "That question node is not a parent of this measure")

                prev = (session.query(model.QnodeMeasure)
                    .filter(model.QnodeMeasure.qnode_id == parent_id,
                            model.QnodeMeasure.survey_id == measure.survey_id,
                            model.QnodeMeasure.seq < son['seq'])
                    .order_by(model.QnodeMeasure.seq.desc())
                    .first())
                next_ = (session.query(model.QnodeMeasure)
                    .filter(model.QnodeMeasure.qnode_id == parent_id,
                            model.QnodeMeasure.survey_id == measure.survey_id,
                            model.QnodeMeasure.seq > son['seq'])
                    .order_by(model.QnodeMeasure.seq)
                    .first())

                if prev is not None:
                    son['prev'] = str(prev.measure_id)
                if next_ is not None:
                    son['next'] = str(next_.measure_id)

            else:
                son['survey'] = to_son(measure.survey)

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
                    .filter(model.Measure.survey_id == self.survey_id)\
                    .filter(model.QnodeMeasure.qnode_id == None)
            elif orphan != '' and falsy(orphan):
                # Non-orphans only
                query = session.query(model.Measure)\
                    .join(model.QnodeMeasure)\
                    .filter(model.Measure.survey_id == self.survey_id)
            else:
                # All measures
                query = session.query(model.Measure)\
                    .filter_by(survey_id=self.survey_id)

            if term != '':
                query = query.filter(
                    model.Measure.title.ilike(r'%{}%'.format(term)))

            query = self.paginate(query)

            measures = query.all()

            to_son = ToSon(include=[
                # Fields to match from any visited object
                r'/id$',
                r'/title$',
                r'/intent$',
                r'/seq$',
                r'/survey/tracking_id$',
                # Descend into nested objects
                r'/[0-9]+$',
                r'/survey$',
            ])
            sons = to_son(measures)

            for mson, measure in zip(sons, measures):
                mson['orphan'] = len(measure.parents) == 0

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    def query_children_of(self, qnode_id):
        with model.session_scope() as session:
            # Only children of a certain qnode
            qnode = session.query(model.QuestionNode)\
                .get((qnode_id, self.survey_id))
            measures = qnode.measures

            to_son = ToSon(include=[
                # Fields to match from any visited object
                r'/id$',
                r'/title$',
                r'/seq$',
                r'/survey/tracking_id$',
                # Descend into nested objects
                r'/[0-9]+$',
                r'/survey$',
            ])
            sons = to_son(measures)

            # Add seq field to measures, because it's not available on the
            # measure objects themselves: the ordinal lives in a separate
            # association table.
            measure_seq = qnode.measure_seq
            for mson, seq in zip(sons, measure_seq):
                mson['seq'] = seq

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
                measure = model.Measure(survey_id=self.survey_id)
                session.add(measure)
                self._update(measure, self.request_son)
                session.flush()

                for parent_id in parent_ids:
                    qnode = session.query(model.QuestionNode)\
                        .get((parent_id, self.survey_id))
                    if qnode is None:
                        raise handlers.ModelError("No such question node")
                    qnode.measures.append(measure)
                    qnode.qnode_measures.reorder()
                    qnode.update_stats_ancestors()
                measure_id = str(measure.id)
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

        self.check_editable()

        try:
            with model.session_scope() as session:
                measure = session.query(model.Measure)\
                    .get((measure_id, self.survey_id))
                if measure is None:
                    raise handlers.MissingDocError("No such measure")

                if len(parent_ids) > 0:
                    # Just unlink from qnodes
                    for parent_id in parent_ids:
                        qnode = session.query(model.QuestionNode)\
                            .get((parent_id, self.survey_id))
                        if qnode is None:
                            raise handlers.MissingDocError(
                                "No such question node")
                        if measure not in qnode.measures:
                            raise handlers.ModelError(
                                "Measure does not belong to that question node")
                        qnode.measures.remove(measure)
                        qnode.qnode_measures.reorder()
                        qnode.update_stats_ancestors()
                else:
                    if len(measure.parents) > 0:
                        raise handlers.ModelError("Measure is in use")
                    session.delete(measure)
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
                    .get((measure_id, self.survey_id))
                if measure is None:
                    raise ValueError("No such object")
                self._update(measure, self.request_son)

                for parent_id in parent_ids:
                    # Add links to parents. Links can't be removed like this;
                    # use the delete method instead.
                    new_parent = session.query(model.QuestionNode)\
                        .get((parent_id, self.survey_id))
                    if new_parent is None:
                        raise handlers.ModelError("No such question node")
                    if new_parent in measure.parents:
                        self.reasons.append('Already a child of %s' % new_parent.title)
                        continue
                    self.reasons.append('Added to %s' % new_parent.title)
                    for old_parent in list(measure.parents):
                        if str(old_parent.hierarchy_id) == str(new_parent.hierarchy_id):
                            old_parent.measures.remove(measure)
                            old_parent.qnode_measures.reorder()
                            self.reasons.append('Moved from %s' % old_parent.title)
                    new_parent.measures.append(measure)
                    new_parent.qnode_measures.reorder()
                    new_parent.update_stats_ancestors()
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such measure")
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
                    .get((qnode_id, self.survey_id))
                reorder(
                    qnode.qnode_measures, self.request_son,
                    id_attr='measure_id')

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
        update('intent', son)
        update('inputs', son)
        update('scenario', son)
        update('questions', son)
        update('response_type', son)
