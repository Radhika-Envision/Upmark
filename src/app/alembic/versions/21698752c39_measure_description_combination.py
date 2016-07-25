"""Combining measure description fields into one

Revision ID: 21698752c39
Revises: 38ca8597c70
Create Date: 2016-02-03 04:03:50.237438

"""

# revision identifiers, used by Alembic.
revision = '21698752c39'
down_revision = '38ca8597c70'
branch_labels = None
depends_on = None

import re
import string
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref, sessionmaker, relationship
from sqlalchemy.schema import MetaData
from sqlalchemy.sql import table, column

from guid import GUID


metadata = MetaData()
Base = declarative_base(metadata=metadata)
Session = sessionmaker()


# Frozen model for online conversion of fields
class Survey(Base):
    __tablename__ = 'survey'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)


class Measure(Base):
    __tablename__ = 'measure'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(
        GUID, ForeignKey("survey.id"), nullable=False, primary_key=True)

    description = Column(Text, nullable=True)
    intent = Column(Text, nullable=True)
    inputs = Column(Text, nullable=True)
    scenario = Column(Text, nullable=True)
    questions = Column(Text, nullable=True)


class QuestionNode(Base):
    __tablename__ = 'qnode'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(
        GUID, ForeignKey("survey.id"), nullable=False, primary_key=True)

    description = Column(Text, nullable=True)


def upgrade():
    op.add_column(
        'measure',
        sa.Column('description', sa.Text(), nullable=True))

    session = Session(bind=op.get_bind())
    for m in session.query(Measure).all():
        upgrade_measure(m)
    for q in session.query(QuestionNode).all():
        upgrade_qnode(q)
    session.flush()

    op.drop_column('measure', 'questions')
    op.drop_column('measure', 'intent')
    op.drop_column('measure', 'scenario')
    op.drop_column('measure', 'inputs')


def downgrade():
    op.add_column(
        'measure',
        sa.Column('inputs', sa.TEXT()))
    op.add_column(
        'measure',
        sa.Column('scenario', sa.TEXT()))
    op.add_column(
        'measure',
        sa.Column('intent', sa.TEXT()))
    op.add_column(
        'measure',
        sa.Column('questions', sa.TEXT()))

    session = Session(bind=op.get_bind())
    for q in session.query(QuestionNode).all():
        downgrade_qnode(q)
    for m in session.query(Measure).all():
        downgrade_measure(m)
    session.flush()

    op.drop_column('measure', 'description')


def upgrade_qnode(qnode):
    if qnode.description:
        qnode.description = plain_text_to_markdown(qnode.description)


def downgrade_qnode(qnode):
    if qnode.description:
        qnode.description = markdown_to_plain_text(qnode.description)


def upgrade_measure(measure):
    desc = []
    if measure.intent:
        desc.append("# Intent")
        desc.append(plain_text_to_markdown(measure.intent).strip())
    if measure.inputs:
        desc.append("# Inputs")
        desc.append(plain_text_to_markdown(measure.inputs).strip())
    if measure.scenario:
        desc.append("# Scenario")
        desc.append(plain_text_to_markdown(measure.scenario).strip())
    if measure.questions:
        desc.append("# Questions")
        desc.append(plain_text_to_markdown(measure.questions).strip())

    if desc:
        measure.description = '\n\n'.join(desc).strip()


def downgrade_measure(measure):
    if not measure.description:
        return

    parts = {
        'intent': [],
        'inputs': [],
        'scenario': [],
        'questions': [],
    }
    title = 'intent'
    for l in measure.description.split('\n'):
        match = re.match(r'# (.*)', l)
        if match:
            new_title = match.group(1).lower()
            if new_title in parts:
                title = new_title
                continue
        parts[title].append(l)

    for k, v in parts.items():
        if v:
            text = '\n'.join(v)
            text = markdown_to_plain_text(text).strip()
            setattr(measure, k, text)


def plain_text_to_markdown(text):
    # Markdown has no alpha lists, so use numbers. These can be style later
    # using CSS. Also, check for nested lists. Current text uses nested lists
    # like:
    #
    # 1. Foo
    # a) Foo one
    # b) Foo two
    # 2. Bar
    # a) Bar one
    #
    # So transform it to:
    #
    # 1. Foo
    #     1. Foo one
    #     1. Foo two
    # 1. Bar
    #     1. Bar one
    #
    # There are no mutli-line paragraphs.
    list_types = []
    ls = []
    LIST_PATTERN = re.compile(r'^ *([0-9]{1,2}\.|[a-z]{1,2}\)|[-–*]) *')
    for l in text.split('\n'):
        if not l:
            ls.append(l)
            continue
        match = LIST_PATTERN.match(l)
        if match:
            if match.group(1)[0] in string.ascii_letters:
                list_type = 'alpha'
            elif match.group(1)[0] in string.digits:
                list_type = 'num'
            else:
                list_type = 'bullet'
            if len(list_types) == 0 or list_types[-1] != list_type:
                if list_type in list_types:
                    # Going back to top-level list
                    list_types = [list_type]
                else:
                    list_types.append(list_type)
        else:
            list_types = []
        if len(list_types) > 0:
            prefix = ("    " * (len(list_types) - 1))
            if list_types[-1] in {'alpha', 'num'}:
                # Markdown always uses numbers for ordered lists
                prefix += "1. "
            else:
                # Domador uses dashes for unordered lists
                prefix += "- "
            l = LIST_PATTERN.sub(prefix, l)
        ls.append(l)
    text = '\n'.join(ls)

    # Assume all line breaks are paragraph endings
    text = text.replace('\n', '\n\n')

    return text


def markdown_to_plain_text(text):
    # Try to undo transforms of plain_text_to_markdown, but don't do anything
    # else fancy
    list_types = []
    ordinals = []
    ls = []
    LIST_PATTERN = re.compile(r'^( *)([0-9]\.|[-*]) ', flags=re.MULTILINE)

    max_depth = 0
    for m in LIST_PATTERN.finditer(text):
        depth = len(m.group(1)) // 4
        max_depth = max(max_depth, depth)

    if max_depth % 2 == 0:
        num_modulo = 1
    else:
        num_modulo = 0

    for l in text.split('\n'):
        if not l:
            ls.append(l)
            continue

        match = LIST_PATTERN.match(l)
        if match:
            depth = len(match.group(1)) // 4
            list_types = list_types[:depth]
            if len(list_types) < depth + 1:
                list_types.append(None)
            if match.group(2)[0] in string.digits:
                list_types[-1] = 'ol'
            else:
                list_types[-1] = 'ul'
            if list_types[-1] == 'ol':
                num_depth = list_types.count('ol')
                ordinals = ordinals[:num_depth]
                ordinals = ordinals + ([0] * (num_depth - len(ordinals)))
                ordinals[-1] += 1
                if num_depth % 2 == num_modulo:
                    prefix = '%s) ' % chr(ordinals[-1] + 96)
                else:
                    prefix = '%d. ' % ordinals[-1]
            else:
                prefix = '- '
            l = LIST_PATTERN.sub(prefix, l)
        ls.append(l)
    text = '\n'.join(ls)

    text = text.replace('\n\n', '\n')

    return text
