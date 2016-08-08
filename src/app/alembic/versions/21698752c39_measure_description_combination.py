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

import logging
import os
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


log_migration = logging.getLogger('app.migration')


metadata = MetaData()
Base = declarative_base(metadata=metadata)
Session = sessionmaker()


# Frozen model for online conversion of fields
class Survey(Base):
    __tablename__ = 'survey'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    description = Column(Text)


class Hierarchy(Base):
    __tablename__ = 'hierarchy'
    id = Column(GUID, default=uuid.uuid4, primary_key=True)
    survey_id = Column(
        GUID, ForeignKey('survey.id'), nullable=False, primary_key=True)

    description = Column(Text)


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
    os.makedirs('/tmp/aq', exist_ok=True)
    with open('/tmp/aq/orig_desc.log', 'wb') as orig_log, \
            open('/tmp/aq/new_desc.log', 'wb') as new_log:
        logger = ConversionLog(orig_log, new_log)
        for m in session.query(Measure).all():
            upgrade_measure(m, logger, "/#/measure/{0.id}?survey={0.survey_id}")
        for q in session.query(QuestionNode).all():
            upgrade_basic(q, logger, "/#/qnode/{0.id}?survey={0.survey_id}")
        for h in session.query(Hierarchy).all():
            upgrade_basic(h, logger, "/#/hierarchy/{0.id}?survey={0.survey_id}")
        for s in session.query(Survey).all():
            upgrade_basic(s, logger, "/#/survey/{0.id}")
    log_migration.info("Conversion to Markdown is complete.")
    log_migration.info("IMPORTANT: check /tmp/aq/*.log.")
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
    for s in session.query(Survey).all():
        downgrade_basic(s)
    for h in session.query(Hierarchy).all():
        downgrade_basic(h)
    for q in session.query(QuestionNode).all():
        downgrade_qnode(q)
    for m in session.query(Measure).all():
        downgrade_measure(m)
    session.flush()

    op.drop_column('measure', 'description')


class ConversionLog:
    def __init__(self, orig_f, new_f):
        self.orig_f = orig_f
        self.new_f = new_f

    def write(self, url, orig_desc, new_desc):
        header = "-- {}\n".format(url)
        self.orig_f.write(header.encode('utf-8'))
        self.orig_f.write("{}\n\n".format(orig_desc).encode('utf-8'))
        self.new_f.write(header.encode('utf-8'))
        self.new_f.write("{}\n\n".format(new_desc).encode('utf-8'))


def upgrade_basic(entity, logger, header_fmt):
    if entity.description:
        orig_desc = entity.description
        entity.description = plain_text_to_markdown(entity.description)
        logger.write(
            header_fmt.format(entity),
            orig_desc, entity.description)


def downgrade_basic(entity):
    if entity.description:
        entity.description = markdown_to_plain_text(entity.description)


def upgrade_measure(measure, logger, header_fmt):
    desc_orig = []
    desc = []
    if measure.intent:
        desc.append("# Intent")
        desc.append(plain_text_to_markdown(measure.intent).strip())
        desc_orig.append("# Intent")
        desc_orig.append(measure.intent.strip())
    if measure.inputs:
        desc.append("# Inputs")
        desc.append(plain_text_to_markdown(measure.inputs).strip())
        desc_orig.append("# Inputs")
        desc_orig.append(measure.inputs.strip())
    if measure.scenario:
        desc.append("# Scenario")
        desc.append(plain_text_to_markdown(measure.scenario).strip())
        desc_orig.append("# Scenario")
        desc_orig.append(measure.scenario.strip())
    if measure.questions:
        desc.append("# Questions")
        desc.append(plain_text_to_markdown(measure.questions).strip())
        desc_orig.append("# Questions")
        desc_orig.append(measure.questions.strip())

    if desc:
        orig_desc = '\n\n'.join(desc_orig).strip()
        measure.description = '\n\n'.join(desc).strip()
        logger.write(
            header_fmt.format(measure),
            orig_desc, measure.description)


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


LIST_PATTERN = re.compile(r'^ *([0-9]{1,2}[.)]|[a-z]{1,2}[.)]|[-‐‑‒–—―•⁃*]) *')
NEWLINE_PATTERN = re.compile(r'\n+')


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
    # - Baz one
    # - Baz two
    #
    # So transform it to:
    #
    # 1. Foo
    #     1. Foo one
    #     1. Foo two
    # 1. Bar
    #     1. Bar one
    #         - Baz one
    #         - Baz two
    #
    # Some lists are on a single line, like:
    #
    # 1. Foo 2. Baz
    #
    # Some paragraphs span multiple lines, easily identified by starting with a
    # lower-case letter.

    ls_prev = text.split('\n')

    # Step 1: Merge wrapped paragraphs
    ls = []
    for l in ls_prev:
        line = l.strip()
        match_list = LIST_PATTERN.match(line)
        if match_list:
            # Lists will be processed later
            pass
        elif ls and ls[-1] and line and ls[-1][-1] != "." and line[0].islower():
            # Special case: if a line starts with a lower-case letter, and the
            # previous line didn't end with a full-stop, merge this line onto
            # the last one.
            ls[-1] = ls[-1] + " " + line
            continue
        ls.append(line)

    # Step 2: identify and transform nested lists
    list_types = []
    ls_prev = ls
    ls = []
    for l in ls_prev:
        if not l:
            ls.append("")
            continue

        match_list = LIST_PATTERN.match(l)
        if match_list:
            if match_list.group(1)[0] in string.ascii_letters:
                # Use a special regular expression that only matches the same
                # type of delimiter within the line.
                list_type = 'alpha'
                delimiter = match_list.group(1)[-1]
                match_items = alpha_patterns[delimiter].findall(l)
            elif match_list.group(1)[0] in string.digits:
                # Use a special regular expression that only matches the same
                # type of delimiter within the line.
                list_type = 'num'
                delimiter = match_list.group(1)[-1]
                match_items = num_patterns[delimiter].findall(l)
            else:
                # Bullets are special: construct a special regular expression
                # that only matches the same type of bullet within the line.
                list_type = 'bullet'
                bullet_char = match_list.group(1)[0]
                match_items = bullet_pattern(bullet_char).findall(l)
            if len(list_types) == 0 or list_types[-1] != list_type:
                if list_type in list_types:
                    # Going back to higher level list
                    list_types = list_types[:list_types.index(list_type) + 1]
                else:
                    list_types.append(list_type)
            items = [text for _, text in match_items]
        elif ls and ls[-1] and ls[-1][-1] == ':' and l.strip() and l.strip()[-1] in ':;':
            # Special case: if the previous line:
            # - Was a list item
            # - Ended in a colon
            # And the current line:
            # - Is superficially not a list item
            # - Ends in a colon or semicolon
            # Then this line is a sub-paragraph that introduces a sub-list.
            prefix = "    " * len(list_types)
            ls.append(prefix + l.strip())
            continue
        else:
            list_types = []
            items = [l]

        if len(list_types) > 0:
            prefix = "    " * (len(list_types) - 1)
            if list_types[-1] in {'alpha', 'num'}:
                # Markdown always uses numbers for ordered lists
                prefix += "1. "
            else:
                # to-markdown uses asterisks for unordered lists
                prefix += "* "
        else:
            prefix = ""

        for item in items:
            ls.append("{}{}".format(prefix, item.strip()))
    text = '\n'.join(ls)

    # Assume all line breaks are paragraph endings
    text = NEWLINE_PATTERN.sub('\n\n', text)

    return text


num_patterns = {
    '.': re.compile(r' *([0-9]{1,2})[.](.*?(?:[^\w]|$))(?=[0-9]{1,2}[.][^0-9]|$)'),
    ')': re.compile(r' *([0-9]{1,2})[)](.*?(?:[^\w(]|$))(?=[0-9]{1,2}[)][^0-9]|$)')
}
alpha_patterns = {
    '.': re.compile(r' *([a-z])[.](.*?(?:[^\w]|$))(?=[a-z][.].|$)'),
    ')': re.compile(r' *([a-z])[)](.*?(?:[^\w(]|$))(?=[a-z][)].|$)')
}
bullet_patterns = {}


def bullet_pattern(char):
    p = bullet_patterns.get(char)
    if not p:
        regex = r' *(['']{1,2})[.)](.*?(?:[^\w(]|$))(?=[0-9]{1,2}[.)].|$)'
        regex = r' *([' + char + '])(.*?(?:\W|$))(?=[' + char + '].|$)'
        p = re.compile(regex)
        bullet_patterns[char] = p
    return p


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
