import datetime
import logging

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import array, ARRAY
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import cast
from sqlalchemy.types import VARCHAR

from function_asfrom import ColumnFunction
import model


log = logging.getLogger('app.activity')


class unnest_func(ColumnFunction):
    name = 'unnest'
    column_names = ['unnest', 'ordinality']


@compiles(unnest_func)
def _compile_unnest_func(element, compiler, **kw):
    return compiler.visit_function(element, **kw) + " WITH ORDINALITY"


class ActivityError(Exception):
    pass


class Activities:
    UPDATE_WINDOW = datetime.timedelta(hours=2)

    def __init__(self, session):
        self.session = session

    def record(self, subject, ob, verbs):
        '''
        Record an action for an object. If the object was changed in the last
        little while, and the most recent change was by the same subject (user),
        then the last action will be reused and its timestamp will be updated.
        '''
        if len(verbs) == 0:
            log.debug("Not recording %s: no verbs", ob)
            return None;
        log.debug("Record %s %s", ob, verbs)
        desc = ob.action_descriptor
        from_time = datetime.datetime.utcnow() - Activities.UPDATE_WINDOW
        action = (self.session.query(model.Activity)
            .filter(model.Activity.created >= from_time,
                    model.Activity.ob_ids == desc.ob_ids)
            .order_by(model.Activity.created.desc())
            .first())

        if action and str(action.subject_id) == str(subject.id):
            action.ob_refs = desc.ob_refs
            action.message = desc.message
            action.created = datetime.datetime.utcnow()
            vs = set(action.verbs)
            new_vs = list(action.verbs) + [v for v in verbs if v not in vs]
            action.verbs = new_vs
        else:
            action = model.Activity(
                subject_id=subject.id, verbs=verbs, **desc._asdict())
            self.session.add(action)
        return action

    def subscribe(self, observer, ob):
        desc = ob.action_descriptor
        sub = model.Subscription(
            user_id=observer.id,
            ob_type=desc.ob_type,
            ob_refs=desc.ob_ids,
            subscribed=True)
        self.session.add(sub)
        return sub

    def has_subscription(self, observer, ob):
        desc = ob.action_descriptor
        count = (self.session.query(model.Subscription)
            .filter(model.Subscription.user_id == observer.id,
                    model.Subscription.ob_refs.contained_by(desc.ob_refs))
            .count())
        return count > 0

    def subscriptions(self, observer, ob):
        '''
        Get a list of subscriptions that are active for the given object, in
        order of increasing priority. That is, the last item in the list
        determines the actual subscription state.
        '''
        desc = ob.action_descriptor
        subs = list(self.session.query(model.Subscription)
            .filter(model.Subscription.user_id == observer.id,
                    model.Subscription.ob_refs.contained_by(desc.ob_refs))
            .all())
        ob_refs = [str(ref) for ref in desc.ob_refs]
        subs.sort(key=lambda sub: ob_refs.index(str(sub.ob_refs[-1])))
        return subs

    def timeline_query(self, user_id, from_date, until_date, sticky_flags=None):
        '''
        Construct a query that filters the activity stream based on the
        subscriptions of a user.
        @param sticky_flags subset of {'filter', 'include', 'at_top'}.
            'filter': Exclude sticky elements from the timeline, unless
                'include' is also given.
            'include': Include sticky elements.
            'at_top': Sort the results so that sticky elements are first.
            The default is to use all flags.
        '''
        if sticky_flags is None:
            sticky_flags = {'filter', 'include', 'at_top'}

        user = self.session.query(model.AppUser).get(user_id)
        if not user:
            raise ActivityError("No such user")

        oid = user.organisation_id
        filter_purchased = not model.has_privillege(
            user.role, 'author', 'consultant')

        time_filter = ((model.Activity.created > from_date) &
                       (model.Activity.created <= until_date))

        if 'filter' in sticky_flags:
            time_filter = (model.Activity.sticky == False) & time_filter
        if 'include' in sticky_flags:
            time_filter = (model.Activity.sticky == True) | time_filter

        order_cols = [model.Activity.created.desc(),
                    model.Activity.id]
        distinct_cols = [model.Activity.created,
                         model.Activity.id]

        if 'at_top' in sticky_flags:
            order_cols = [model.Activity.sticky.desc()] + order_cols
            distinct_cols = [model.Activity.sticky] + distinct_cols

        query = (self.session.query(model.Activity)
            .filter(time_filter)
            .order_by(*order_cols))

        # Mark activities as subscribed or not
        # Join with the subscription table using the ob_refs field
        act_ref = unnest_func(model.Activity.ob_refs).alias('act_ref')
        broadcast = cast(['broadcast'], ARRAY(VARCHAR))
        query = (query
            .add_columns(
                act_ref.c.unnest,
                act_ref.c.ordinality,
                model.Subscription.subscribed)
            .outerjoin(act_ref, sa.true())
            .outerjoin(
                model.Subscription,
                model.Subscription.ob_refs[1] == act_ref.c.unnest)
            .filter(
                ((model.Subscription.id != None) &
                 (model.Subscription.user_id == user_id)) |
                ((model.Activity.verbs == broadcast) &
                 (model.Activity.ob_type == None)))
            .order_by(act_ref.c.ordinality.desc()))

        # Filter out activities that involve surveys that have not been
        # purchased.
        # Join with survey and purchased_survey tables using ob_refs
        # field
        if filter_purchased:
            query = (query
                .add_columns(
                    ((model.Survey.id == None) |
                     (model.PurchasedSurvey.survey_id != None))
                    .label('purchased'))
                .outerjoin(
                    model.Survey,
                    model.Activity.ob_refs.contains(
                        array([model.Survey.program_id,
                               model.Survey.id])))
                .outerjoin(
                    model.PurchasedSurvey,
                    model.Activity.ob_refs.contains(
                        array([model.PurchasedSurvey.program_id,
                               model.PurchasedSurvey.survey_id])) &
                    (model.PurchasedSurvey.program_id == model.Survey.program_id) &
                    (model.PurchasedSurvey.survey_id == model.Survey.id))
                .filter(
                    (model.PurchasedSurvey.organisation_id == None) |
                    (model.PurchasedSurvey.organisation_id == oid)))

        # Create a subquery so we can discard duplicate subscriptions (based on
        # subscription depth; see use of `unnest` above).
        sub = (query
            .distinct(*distinct_cols)
            .subquery('sub'))

        query = (self.session.query(model.Activity)
            .select_entity_from(sub)
            .filter((sub.c.subscribed == None) |
                     (sub.c.subscribed == True)))

        if filter_purchased:
            query = query.filter(sub.c.purchased == True)

        return query
