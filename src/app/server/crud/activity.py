import datetime

from tornado.escape import json_encode
import tornado.web
import sqlalchemy

import handlers
import model
import logging

from utils import ToSon, truthy, updater


class ActivityHandler(handlers.BaseHandler):

    @tornado.web.authenticated
    def get(self):
        until_date = self.get_argument('until', '')
        if until_date != '':
            until_date = datetime.datetime.fromtimestamp(until_date)
        else:
            until_date = datetime.datetime.utcnow()

        from_date = self.get_argument('from', '')
        if from_date != '':
            until_date = datetime.datetime.fromtimestamp(until_date)
        else:
            from_date = until_date - datetime.timedelta(days=7)

        if (until_date - from_date).days > 31:
            raise handlers.ModelError(
                "Time range is too large")

        with model.session_scope() as session:
            query = (session.query(model.Activity)
                .filter(((model.Activity.created > from_date) &
                         (model.Activity.created <= until_date)) |
                        (model.Activity.sticky == True))
                .order_by(model.Activity.sticky.desc(),
                          model.Activity.created.desc()))

            to_son = ToSon(include=[
                r'^/created$',
                r'/subject$',
                r'/subject/id$',
                r'/subject/name$',
                r'/verbs/?.*$',
                r'/object_desc$',
                r'/object_ids/?.*$',
                r'/[0-9]+$',
            ])
            son = {
                'from': from_date.timestamp(),
                'until': until_date.timestamp(),
                'activities': to_son(query.all())
            }

        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()


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
