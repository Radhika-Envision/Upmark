import datetime

from tornado.escape import json_encode
import tornado.web
import sqlalchemy

import handlers
import model
import logging

from utils import ToSon, truthy, updater


log = logging.getLogger('app.crud.activity')


class ActivityHandler(handlers.BaseHandler):

    TO_SON = ToSon(include=[
        r'/id$',
        r'/created$',
        r'/sticky$',
        r'/subject$',
        r'/subject/name$',
        r'/verbs/?.*$',
        r'/ob_type$',
        r'/ob_ids$',
        r'/object_desc$',
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
            query = session.query(model.Activity)
            date_range = ((model.Activity.created > from_date) &
                          (model.Activity.created <= until_date))
            if include_sticky:
                query = query.filter(
                    date_range | (model.Activity.sticky == True))
            else:
                query = query.filter(
                    date_range & (model.Activity.sticky == False))

            query = query.order_by(
                model.Activity.sticky.desc(),
                model.Activity.created.desc())

            son = {
                'from': from_date.timestamp(),
                'until': until_date.timestamp(),
                'actions': ActivityHandler.TO_SON(query.all())
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
            activity = model.Activity(
                subject_id=self.current_user.id,
                verbs=['broadcast'],
                object_desc=self.request_son['message'],
                sticky=self.request_son['sticky'],
                ob_type=None,
                ob_ids=[],
                ob_refs=[]
            )
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
            if 'object_desc' in self.request_son:
                activity.object_desc = self.request_son['object_desc']
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


class SubscriptionHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self, user_id, object_ids):
        object_ids = object_ids.split('/')
        with model.session_scope() as session:
            user = session.query(model.AppUser).get(user_id)
            if not user:
                raise handlers.MissingDocError("No such user")

            self.check_authz(user)

            subscription = self.get_subscription(session, user_id, object_ids)
            if not subscription:
                raise handlers.MissingDocError("No subscription for that object")

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

    @tornado.web.authenticated
    def put(self, user_id, object_ids):
        object_ids = object_ids.split('/')
        with model.session_scope() as session:
            user = session.query(model.AppUser).get(user_id)
            if not user:
                raise handlers.MissingDocError("No such user")

            self.check_authz(user)

            subscription = self.get_subscription(session, user_id, object_ids)
            if not subscription:
                self.check_exists(
                    session, self.request_son['ob_type'], object_ids)

                subscription = model.Subscription(
                    user_id=user_id,
                    ob_refs=object_ids,
                    ob_type=self.request_son['ob_type'])
            self.update(subscription, self.request_son)

        self.get(user_id, object_ids)

    @tornado.web.authenticated
    def delete(self, user_id, object_ids):
        object_ids = object_ids.split('/')
        with model.session_scope() as session:
            user = session.query(model.AppUser).get(user_id)
            if not user:
                raise handlers.MissingDocError("No such user")

            self.check_authz(user)

            subscription = self.get_subscription(session, user_id, object_ids)
            if not subscription:
                raise model.MissingDocError("No subscription for that object")
            session.delete(subscription)

        self.finish()

    def get_subscription(self, session, user_id, object_ids):
        query = (session.query(model.Subscription)
            .filter(model.Subscription.user_id == user_id,
                    model.Subscription.ob_refs == object_ids))
        try:
            subscription = query.one()
        except sqlalchemy.exc.StatementError as e:
            return None
        return subscription

    def check_exists(self, session, ob_type, ob_refs):
        def arglen(n, min_, max_=None):
            if max_ is None:
                max_ = min_
            if len(ob_refs) < min_ or len(ob_refs) > max_:
                raise handlers.ModelError(
                    "Wrong number of IDs for '%s'" % ob_type)
            
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
            arglen(len(ob_refs), 1, 2)
            query = (session.query(model.Hierarchy)
                .filter(model.Hierarchy.id == ob_refs[0]))
            if len(ob_refs) > 1:
                query = query.filter(model.Hierarchy.survey_id == ob_refs[1])

        elif ob_type == 'qnode':
            arglen(len(ob_refs), 1, 2)
            query = (session.query(model.QuestionNode)
                .filter(model.QuestionNode.id == ob_refs[0]))
            if len(ob_refs) > 1:
                query = query.filter(model.QuestionNode.survey_id == ob_refs[1])

        elif ob_type == 'measure':
            arglen(len(ob_refs), 1, 2)
            query = (session.query(model.Measure)
                .filter(model.Measure.id == ob_refs[0]))
            if len(ob_refs) > 1:
                query = query.filter(model.Measure.survey_id == ob_refs[1])

        elif ob_type == 'submission':
            arglen(len(ob_refs), 1)
            query = (session.query(model.Assessment)
                .filter(model.Assessment.id == ob_refs[0]))

        else:
            raise model.ModelError("Can't subscribe to '%s' type" % ob_type)

        if query.count() == 0:
            raise model.MissingDocError("No such object")

    def check_authz(self, user):
        if self.has_privillege('admin'):
            return
        elif str(user.id) == str(self.current_user.id):
            return
        elif not self.has_privillege('org_admin'):
            raise handlers.AuthzError(
                "You can't view another user's subscriptions.")
        elif str(user.organisation_id) != str(self.current_user.organisation_id):
            raise handlers.AuthzError(
                "You can't view another organisation's user's subscriptions.")

    def update(self, subscription, son):
        '''
        Apply user-provided data to the saved model.
        '''
        update = updater(subscription)
        update('subscribed', son)
