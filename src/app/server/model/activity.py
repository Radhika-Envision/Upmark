__all__ = ['Activity', 'Subscription']

from datetime import datetime
import logging
import time
import uuid

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import backref, relationship
from sqlalchemy.schema import CheckConstraint, Index, UniqueConstraint

from guid import GUID

from .base import Base
from .user import AppUser


class Activity(Base):
    '''
    An event in the activity stream (timeline). This forms a kind of logging
    that can be filtered based on users' subscriptions.
    '''
    __tablename__ = 'activity'
    id = Column(GUID, default=uuid.uuid4, nullable=False, primary_key=True)
    created = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Subject is the user performing the action. The object may also be a user.
    subject_id = Column(GUID, ForeignKey("appuser.id"), nullable=False)
    # Verb is the action being performed by the subject on the object.
    verbs = Column(
        ARRAY(Enum(
            'broadcast',
            'create', 'update', 'state', 'delete', 'undelete',
            'relation', 'reorder_children',
            'report',
            native_enum=False, create_constraint=False)),
        nullable=False)
    # A snapshot of some defining feature of the object at the time the event
    # happened (e.g. title of a measure before it was deleted).
    message = Column(Text)
    sticky = Column(Boolean, nullable=False, default=False)

    # Object reference (the entity being acted upon). The ob_type and ob_id_*
    # columns are for looking up the target object (e.g. to create a hyperlink).
    ob_type = Column(Enum(
        'organisation', 'user',
        'program', 'survey', 'qnode', 'measure', 'response_type',
        'submission', 'rnode', 'response',
        'custom_query',
        native_enum=False))
    ob_ids = Column(ARRAY(GUID), nullable=False)
    # The ob_refs column contains all relevant IDs including e.g. parent
    # categories, and is used for filtering.
    ob_refs = Column(ARRAY(GUID), nullable=False)

    __table_args__ = (
        # Index `created` column to allow fast filtering by date ranges across
        # all users.
        # Note Postgres' default index is btree, which supports ordered index
        # scanning.
        Index('activity_created_index', created),
        # A multi-column index that has the subject's ID first, so we can
        # quickly list the recent activity of a user.
        Index('activity_subject_id_created_index', subject_id, created),
        # Sticky activities are queried without respect to time, so a separate
        # index is needed for them.
        Index('activity_sticky_index', sticky,
              postgresql_where=(sticky == True)),
        CheckConstraint(
            "(verbs @> ARRAY['broadcast']::varchar[] or ob_type != null)",
            name='activity_broadcast_constraint'),
        CheckConstraint(
            """verbs <@ ARRAY[
                'broadcast',
                'create', 'update', 'state', 'delete', 'undelete',
                'relation', 'reorder_children',
                'report'
            ]::varchar[]""",
            name='activity_verbs_check'),
        CheckConstraint(
            'ob_type = null or array_length(verbs, 1) > 0',
            name='activity_verbs_length_constraint'),
        CheckConstraint(
            'ob_type = null or array_length(ob_ids, 1) > 0',
            name='activity_ob_ids_length_constraint'),
        CheckConstraint(
            'ob_type = null or array_length(ob_refs, 1) > 0',
            name='activity_ob_refs_length_constraint'),
    )

    subject = relationship(AppUser)


class Subscription(Base):
    '''Subscribes a user to events related to some object'''
    __tablename__ = 'subscription'
    id = Column(GUID, default=uuid.uuid4, nullable=False, primary_key=True)
    created = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(GUID, ForeignKey("appuser.id"), nullable=False)
    subscribed = Column(Boolean, nullable=False)

    # Object reference; does not include parent objects. One day an index might
    # be needed on the ob_refs column; if you want to use GIN, see:
    # http://www.postgresql.org/docs/9.4/static/gin-intro.html
    # http://stackoverflow.com/questions/19959735/postgresql-gin-index-on-array-of-uuid
    ob_type = Column(Enum(
        'organisation', 'user',
        'program', 'survey', 'qnode', 'measure', 'response_type',
        'submission', 'rnode', 'response',
        'custom_query',
        native_enum=False))
    ob_refs = Column(ARRAY(GUID), nullable=False)

    __table_args__ = (
        # Index to allow quick lookups of subscribed objects for a given user
        Index('subscription_user_id_index', user_id),
        UniqueConstraint(
            user_id, ob_refs,
            name='subscription_user_ob_refs_unique_constraint'),
        CheckConstraint(
            'ob_type = null or array_length(ob_refs, 1) > 0',
            name='subscription_ob_refs_length_constraint'),
    )

    user = relationship(AppUser, backref='subscriptions')
