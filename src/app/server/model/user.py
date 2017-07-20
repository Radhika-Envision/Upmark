__all__ = [
    'AppUser',
    'Organisation',
    'OrgLocation',
    'OrgMeta',
]

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, \
    ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import backref, relationship
from sqlalchemy.schema import CheckConstraint
from sqlalchemy.sql import func

from .base import Base
from .guid import GUID
from .observe import Observable
from .password import Password


class Organisation(Observable, Base):
    __tablename__ = 'organisation'
    id = Column(GUID, default=GUID.gen, primary_key=True)

    name = Column(Text, nullable=False)
    url = Column(Text, nullable=True)
    created = Column(DateTime, default=datetime.utcnow, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)

    @property
    def ob_title(self):
        return self.name

    @property
    def ob_type(self):
        return 'organisation'

    @property
    def ob_ids(self):
        return [self.id]

    @property
    def action_lineage(self):
        return [self]

    __table_args__ = (
        Index('organisation_name_key', func.lower(name), unique=True),
    )

    def __repr__(self):
        return "Organisation(name={})".format(self.name)


class OrgMeta(Base):
    __tablename__ = 'org_meta'
    id = Column(GUID, default=GUID.gen, primary_key=True)
    organisation_id = Column(
        GUID, ForeignKey("organisation.id"), nullable=False)

    ownership = Column(Enum(
        'government run', 'government owned', 'private', 'shareholder',
        native_enum=False))
    structure = Column(Enum('internal', 'corporation', native_enum=False))
    asset_types = Column(ARRAY(Enum(
        'water wholesale', 'water local',
        'wastewater wholesale', 'wastewater local',
        native_enum=False, create_constraint=False)))
    regulation_level = Column(Enum(
        'extensive', 'partial', 'none', native_enum=False))

    value_water_ws = Column(Float)
    value_water_l = Column(Float)
    value_wastewater_ws = Column(Float)
    value_wastewater_l = Column(Float)

    operating_cost = Column(Float)
    revenue = Column(Float)
    number_fte = Column(Float)
    number_fte_ext = Column(Float)

    population_served = Column(Integer)
    number_of_customers = Column(Integer)
    volume_supplied = Column(Float)
    volume_collected = Column(Float)

    organisation = relationship(
        Organisation,
        backref=backref('meta', uselist=False, cascade="all, delete-orphan"))

    __table_args__ = (
        CheckConstraint(
            """asset_types <@ ARRAY[
                'water wholesale', 'water local',
                'wastewater wholesale', 'wastewater local'
            ]::varchar[]""",
            name='org_meta_asset_types_check'),
    )


class OrgLocation(Base):
    __tablename__ = 'org_location'
    id = Column(GUID, default=GUID.gen, primary_key=True)
    organisation_id = Column(
        GUID, ForeignKey("organisation.id"), nullable=False)

    # Fields loosely match those returned by OSM's Nominatim service:
    # http://wiki.openstreetmap.org/wiki/Nominatim

    description = Column(Text, nullable=False)
    language = Column(Text)
    licence = Column(Text)

    country = Column(Text)
    # Region/prefecture/state district
    region = Column(Text)
    county = Column(Text)
    state = Column(Text)
    postcode = Column(Text)
    city = Column(Text)
    suburb = Column(Text)

    lon = Column(Float)
    lat = Column(Float)

    organisation = relationship(
        Organisation,
        backref=backref('locations', cascade="all, delete-orphan"))


ONE_DAY_S = 60 * 60 * 24


class AppUser(Observable, Base):
    __tablename__ = 'appuser'
    id = Column(GUID, default=GUID.gen, primary_key=True)
    organisation_id = Column(
        GUID, ForeignKey("organisation.id"), nullable=False)

    email = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    password = Column(Password, nullable=False)
    role = Column(Enum(
        'super_admin', 'admin', 'author', 'authority', 'consultant',
        'org_admin', 'clerk',
        native_enum=False), nullable=False)
    created = Column(DateTime, default=datetime.utcnow, nullable=False)
    deleted = Column(Boolean, default=False, nullable=False)

    # Notification metadata.
    # NULL email_time means no notifications have ever been sent.
    email_time = Column(DateTime, nullable=True)
    # Email interval is the time between sending details of the activities a
    # user is subscribed to. Units are seconds. 0 means notifications are
    # disabled.
    email_interval = Column(Integer, default=ONE_DAY_S, nullable=False)

    @property
    def ob_title(self):
        return self.name

    @property
    def ob_type(self):
        return 'user'

    @property
    def ob_ids(self):
        return [self.id]

    @property
    def action_lineage(self):
        return [self.organisation, self]

    __table_args__ = (
        Index('appuser_email_key', func.lower(email), unique=True),
        # Index on name because it's used for sorting
        Index('appuser_name_index', func.lower(name)),
        CheckConstraint(
            'email_interval BETWEEN 0 AND 1209600',
            name='appuser_email_interval_constraint'),
    )

    def __repr__(self):
        return "AppUser(email={})".format(self.email)


Password.instrument(AppUser.password)


AppUser.organisation = relationship(Organisation)
Organisation.users = relationship(
    AppUser, back_populates="organisation", passive_deletes=True,
    primaryjoin=(Organisation.id == AppUser.organisation_id) &
                (AppUser.deleted == False))
