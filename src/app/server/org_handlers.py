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

from utils import to_dict, simplify, normalise

class OrgHandler(handlers.Paginate, handlers.BaseHandler):
    @tornado.web.authenticated
    def get(self, org_id):
        if org_id == "":
            self.query()
            return

        with model.session_scope() as session:
            try:
                org = session.query(model.Organisation).get(org_id)
                if org is None:
                    raise ValueError("No such object")
            except (sqlalchemy.exc.StatementError, ValueError):
                raise handlers.MissingDocError("No such organisation")
            son = to_dict(org)
            son = simplify(son)
            son = normalise(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(son))
        self.finish()

    def query(self):
        sons = []
        with model.session_scope() as session:
            query = session.query(model.Organisation)
            term = self.get_argument('term', None)
            if term is not None:
                query = query.filter(
                    model.Organisation.name.ilike(r'%{}%'.format(term)))
            query = query.order_by(model.Organisation.name)
            query = self.paginate(query)
            for ob in query.all():
                son = to_dict(
                    ob, include={'id', 'name', 'region', 'number_of_customers'})
                son = simplify(son)
                son = normalise(son)
                sons.append(son)
        self.set_header("Content-Type", "application/json")
        self.write(json_encode(sons))
        self.finish()

    @handlers.authz('admin')
    def post(self, org_id):
        '''
        Create a new organisation.
        '''
        if org_id != '':
            raise handlers.MethodError(
                "Can't use POST for existing organisation.")

        son = json_decode(self.request.body)
        try:
            with model.session_scope() as session:
                org = model.Organisation()
                self._update(org, son)
                session.add(org)
                session.flush()
                session.expunge(org)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        self.get(org.id)

    @handlers.authz('admin', 'org_admin')
    def put(self, org_id):
        '''
        Update an existing organisation.
        '''
        if org_id == '':
            raise handlers.MethodError(
                "Can't use PUT for new organisations (no ID).")

        if self.current_user.role == 'org_admin' \
                and str(self.organisation.id) != org_id:
            raise handlers.AuthzError(
                "You can't modify another organisation's information.")

        son = json_decode(self.request.body)
        try:
            with model.session_scope() as session:
                org = session.query(model.Organisation).get(org_id)
                if org is None:
                    raise ValueError("No such object")
                self._update(org, son)
                session.add(org)
        except sqlalchemy.exc.IntegrityError as e:
            raise handlers.ModelError.from_sa(e)
        except (sqlalchemy.exc.StatementError, ValueError):
            raise handlers.MissingDocError("No such organisation")
        self.get(org_id)

    def _update(self, org, son):
        '''
        Apply organisation-provided data to the saved model.
        '''
        if son.get('name', '') != '':
            org.name = son['name']
        if son.get('url', '') != '':
            org.url = son['url']
        if son.get('numberOfCustomers', '') != '':
            org.number_of_customers = son['numberOfCustomers']
        if son.get('region', '') != '':
            org.region = son['region']
