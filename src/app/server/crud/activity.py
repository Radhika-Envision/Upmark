import datetime
from itertools import product

from tornado.escape import json_encode
import tornado.web
import sqlalchemy
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql.expression import cast
from sqlalchemy.types import VARCHAR

import handlers
import model
import logging

from utils import ToSon, truthy, updater


log = logging.getLogger('app.crud.activity')


class ActivityHandler(handlers.BaseHandler):

    TO_SON = ToSon(include=[
        r'/id$',
        r'/created$',
        r'/message$',
        r'/sticky$',
        r'/subject$',
        r'/subject/name$',
        r'/verbs/?.*$',
        r'/ob_type$',
        r'/ob_ids$',
        r'/object_ids/?.*$',
        r'/[0-9]+$',
    ], exclude=[
        r'/subject/created$',
    ])

    @tornado.web.authenticated
    def get(self, activity_id):
        if activity_id == '':
            return self.query()

        raise handlers.MethodError("GET for single activity is not implemented")

    def query(self):
        until_date = self.get_argument('until', '')
        if until_date != '':
            until_date = datetime.datetime.fromtimestamp(float(until_date))
        else:
            until_date = datetime.datetime.utcnow()

        period = self.get_argument('period', '')
        if period != '':
            period = datetime.timedelta(seconds=float(period))
        else:
            period = datetime.timedelta(days=7)

        if period.days > 31:
            raise handlers.ModelError("Time period is too large")

        from_date = until_date - period

        # Only show sticky elements when viewing current time period
        offset = abs((until_date - datetime.datetime.utcnow()).total_seconds())
        include_sticky = offset < period.total_seconds() / 2

        with model.session_scope() as session:
            def filter_by_subscriptions(query):
                # Join with the subscription table using the ob_refs field
                broadcast = cast(['broadcast'], ARRAY(VARCHAR))
                query = query.outerjoin(
                    model.Subscription,
                    model.Activity.ob_refs.contains(model.Subscription.ob_refs))
                query = query.filter(
                    ((model.Subscription.id != None) &
                     (model.Subscription.user_id == self.current_user.id)) |
                    ((model.Activity.verbs == broadcast) &
                     (model.Activity.ob_type == None)))
                return query

            query = (session.query(model.Activity)
                .filter(model.Activity.created > from_date,
                        model.Activity.created <= until_date,
                        model.Activity.sticky == False))

            query = filter_by_subscriptions(query)

            query = query.order_by(model.Activity.created.desc())
            non_sticky = query.all()

            if include_sticky:
                query = (session.query(model.Activity)
                    .filter(model.Activity.sticky == True))
                query = filter_by_subscriptions(query)
                query = query.order_by(model.Activity.created.desc())
                sticky = query.all()
            else:
                sticky = []

            son = {
                'from': from_date.timestamp(),
                'until': until_date.timestamp(),
                'actions': ActivityHandler.TO_SON(sticky + non_sticky)
            }

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def post(self, activity_id):
        if activity_id != '':
            raise handlers.ModelError("Can't specify ID for new activity")

        if len(self.request_son['message']) < 3:
            raise handlers.ModelError("Message is too short")

        with model.session_scope() as session:
            if self.request_son['to'] == 'org':
                self.check_privillege('org_admin')
                ob = (session.query(model.Organisation)
                    .get(self.current_user.organisation_id))
                if ob is None:
                    raise handlers.ModelError('No such organisation')
            elif self.request_son['to'] == 'all':
                self.check_privillege('admin')
                ob = None
            else:
                raise handlers.ModelError('Unrecognised recipient')

            activity = model.Activity(
                subject_id=self.current_user.id,
                verbs=['broadcast'],
                message=self.request_son['message'],
                sticky=self.request_son['sticky']
            )

            if ob:
                desc = ob.action_descriptor
                activity.ob_type = desc.ob_type
                activity.ob_ids = desc.ob_ids
                activity.ob_refs = desc.ob_refs
            else:
                activity.ob_type = None
                activity.ob_ids = []
                activity.ob_refs = []

            session.add(activity)
            session.flush()
            self.check_create(activity)
            son = ActivityHandler.TO_SON(activity)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def put(self, activity_id):
        with model.session_scope() as session:
            activity = (session.query(model.Activity)
                .get(activity_id))
            if not activity:
                raise handlers.MissingDocError("No such activity")

            self.check_modify(activity)

            if 'sticky' in self.request_son:
                activity.sticky = self.request_son['sticky']
            if 'message' in self.request_son:
                activity.message = self.request_son['message']
            son = ActivityHandler.TO_SON(activity)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    @tornado.web.authenticated
    def delete(self, activity_id):
        with model.session_scope() as session:
            activity = (session.query(model.Activity)
                .get(activity_id))
            if not activity:
                raise handlers.MissingDocError("No such activity")
            self.check_delete(activity)
            session.delete(activity)

        self.set_header("Content-Type", "text/plain")
        self.write("Deleted")
        self.finish()

    def check_create(self, activity):
        if activity.verbs != ['broadcast']:
            raise handlers.AuthzError(
                "You can't create a non-broadcast activity")
        self.check_modify(activity)

    def check_modify(self, activity):
        if self.has_privillege('admin'):
            return
        elif self.has_privillege('org_admin'):
            org = activity.subject.organisation
            if str(org.id) != str(self.current_user.organisation_id):
                raise handlers.AuthzError(
                    "You can't modify another organisation's activity")
        else:
            raise handlers.AuthzError(
                "You can't modify activities")

    def check_delete(self, activity):
        if activity.verbs != ['broadcast']:
            raise handlers.AuthzError(
                "You can't delete a non-broadcast activity")
        self.check_modify(activity)


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
            return None;
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

    def is_subscribed(self, observer, ob):
        '''
        Check whether an object would show up in the user's timeline.
        @return True if the user is subscribed to this object or its parents,
        False if the user has explicitly unsubscribed, or None if no
        subscription has been made yet (effectively False).
        '''
        subs = self.subscriptions(observer, ob)
        if len(subs) == 0:
            return None
        return subs[-1].subscribed

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


class SubscriptionHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, ob_type, ids):
        if ob_type != '':
            self.query(ob_type, ids.split(','))
            return

        subscription_id = ids
        with model.session_scope() as session:
            subscription = (session.query(model.Subscription)
                .get(subscription_id))
            if not subscription:
                raise handlers.MissingDocError("No such subscription")

            if subscription.user_id != self.current_user.id:
                raise handlers.ModelError(
                    "Can't view another user's subscriptions")

            to_son = ToSon(include=[
                r'/created$',
                r'/user_id$',
                r'/subscribed$',
                r'/ob_type$',
                r'/ob_refs/?.*$',
            ])
            son = to_son(subscription)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self, ob_type, object_ids):
        with model.session_scope() as session:
            ob = self.get_ob(session, ob_type, object_ids)
            if not ob:
                raise handlers.MissingDocError("No such object")

            act = Activities(session)
            subs = act.subscriptions(self.current_user, ob)
            subscription_map = {
                tuple(sub.ob_refs): sub.subscribed
                for sub in act.subscriptions(self.current_user, ob)}
            subscription_id_map = {
                tuple(sub.ob_refs): sub.id
                for sub in act.subscriptions(self.current_user, ob)}

            lineage = [{
                'id': subscription_id_map.get(tuple(item.ob_ids), None),
                'title': hasattr(item, 'title') and item.title or item.name,
                'ob_type': item.ob_type,
                'ob_ids': item.ob_ids,
                'subscribed': subscription_map.get(tuple(item.ob_ids), None)
            } for item in ob.action_lineage]

            to_son = ToSon(include=[
                r'/id$',
                r'/title$',
                r'/subscribed$',
                r'/ob_type$',
                r'/ob_ids/?.*$',
                r'/[0-9]+$',
            ])
            sons = to_son(lineage)

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @tornado.web.authenticated
    def post(self, ob_type, object_ids):
        object_ids = object_ids.split(',')
        log.error("%s", object_ids)

        if ob_type == '':
            raise handlers.ModelError(
                "Object type required when creating a subscription")

        try:
            with model.session_scope() as session:
                ob = self.get_ob(session, ob_type, object_ids)
                if not ob:
                    raise handlers.MissingDocError("No such object")

                acts = Activities(session)
                subscription = acts.subscribe(self.current_user, ob)
                subscription.subscribed = self.request_son.get(
                    'subscribed', False)

                session.flush()
                subscription_id = str(subscription.id)

        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)

        self.get('', subscription_id)

    @tornado.web.authenticated
    def put(self, ob_type, subscription_id):
        if ob_type != '':
            raise handlers.ModelError(
                "Can't provide object type when updating a subscription")

        with model.session_scope() as session:
            subscription = (session.query(model.Subscription)
                .get(subscription_id))

            if not subscription:
                raise handlers.MissingDocError("No such subscription")

            if subscription.user_id != self.current_user.id:
                raise handlers.AuthzError(
                    "You can't modify another user's subscriptions")

            subscription.subscribed = self.request_son.get('subscribed', False)

            subscription_id = str(subscription.id)

        self.get('', subscription_id)

    @tornado.web.authenticated
    def delete(self, ob_type, subscription_id):
        if ob_type != '':
            raise handlers.ModelError(
                "Can't provide object type when deleting a subscription")

        with model.session_scope() as session:
            subscription = (session.query(model.Subscription)
                .get(subscription_id))

            if not subscription:
                raise model.MissingDocError("No subscription for that object")

            if subscription.user_id != self.current_user.id:
                raise handlers.AuthzError(
                    "You can't modify another user's subscriptions")

            session.delete(subscription)

        self.finish()

    def get_ob(self, session, ob_type, ob_refs):
        def arglen(n, min_, max_=None):
            if max_ is None:
                max_ = min_
            if len(ob_refs) < min_ or len(ob_refs) > max_:
                raise handlers.ModelError(
                    "Wrong number of IDs for %s" % ob_type)
            
        if ob_type == 'organisation':
            arglen(len(ob_refs), 1)
            query = (session.query(model.Organisation)
                .filter(model.Organisation.id == ob_refs[0]))

        elif ob_type == 'user':
            arglen(len(ob_refs), 1)
            query = (session.query(model.AppUser)
                .filter(model.AppUser.id == ob_refs[0]))

        elif ob_type == 'program':
            arglen(len(ob_refs), 1)
            query = (session.query(model.Survey)
                .filter(model.Survey.id == ob_refs[0]))

        elif ob_type == 'survey':
            arglen(len(ob_refs), 2, 2)
            query = (session.query(model.Hierarchy)
                .filter(model.Hierarchy.id == ob_refs[0],
                        model.Hierarchy.survey_id == ob_refs[1]))

        elif ob_type == 'qnode':
            arglen(len(ob_refs), 2, 2)
            query = (session.query(model.QuestionNode)
                .filter(model.QuestionNode.id == ob_refs[0],
                        model.QuestionNode.survey_id == ob_refs[1]))

        elif ob_type == 'measure':
            arglen(len(ob_refs), 2, 2)
            query = (session.query(model.Measure)
                .filter(model.Measure.id == ob_refs[0],
                        model.Measure.survey_id == ob_refs[1]))

        elif ob_type == 'submission':
            arglen(len(ob_refs), 1)
            query = (session.query(model.Assessment)
                .filter(model.Assessment.id == ob_refs[0]))

        else:
            raise model.ModelError("Can't subscribe to '%s' type" % ob_type)

        return query.first()

    def check_authz(self, user):
        if self.has_privillege('admin'):
            return
        elif str(user.id) == str(self.current_user.id):
            return
        elif not self.has_privillege('org_admin'):
            raise handlers.AuthzError(
                "You can't access another user's subscriptions.")
        elif str(user.organisation_id) != str(self.current_user.organisation_id):
            raise handlers.AuthzError(
                "You can't access another organisation's user's subscriptions.")

    def update(self, subscription, son):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(subscription)
        update('subscribed', son)


class CardHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self):
        sons = []
        to_son = ToSon(include=[
            r'.*'
        ])
        with model.session_scope() as session:
            org_id = self.current_user.organisation_id
            org = (session.query(model.Organisation).get(org_id))
            sons.append(to_son({
                'title': org.name,
                'created': org.created,
                'ob_type': 'organisation',
                'ob_ids': [org.id],
            }))

            if self.has_privillege('author', 'consultant'):
                surveys = (session.query(model.Survey)
                    .filter(model.Survey.finalised_date == None)
                    .order_by(model.Survey.created.desc())
                    .limit(2)
                    .all())
                sons += to_son([{
                    'title': s.title,
                    'created': s.created,
                    'ob_type': 'program',
                    'ob_ids': [s.id],
                } for s in surveys])

            if self.has_privillege('clerk'):
                assessments = (session.query(model.Assessment)
                    .filter(model.Assessment.organisation_id == org_id)
                    .order_by(model.Assessment.created.desc())
                    .limit(2)
                    .all())
                sons += to_son([{
                    'title': a.title,
                    'created': a.created,
                    'ob_type': 'submission',
                    'ob_ids': [a.id],
                } for a in assessments])

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()
