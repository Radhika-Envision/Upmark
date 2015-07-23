import datetime
import time
import unittest
from unittest import mock
import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String

from guid import GUID
import model
from utils import to_dict, simplify, normalise, denormalise, truthy, falsy, \
    UtilException, ToSon
import unittest


class TestNode(model.Base):
    __tablename__ = 'testnode'
    id_col = Column(GUID, primary_key=True)
    int_col = Column(Integer)
    bool_col = Column(Boolean)
    string_col = Column(String)
    float_col = Column(String)
    date_col = Column(DateTime)

    @property
    def parent(self):
        try:
            return self._parent
        except AttributeError:
            return None

    @parent.setter
    def parent(self, value):
        self._parent = value


class ConversionTest(unittest.TestCase):

    def test_truthy(self):
        self.assertTrue(truthy(True))
        self.assertTrue(truthy('True'))
        self.assertTrue(truthy('true'))
        self.assertTrue(truthy('yes'))
        self.assertTrue(truthy(1))
        self.assertTrue(truthy('1'))
        self.assertFalse(truthy('False'))

    def test_falsey(self):
        self.assertTrue(falsy(False))
        self.assertTrue(falsy('False'))
        self.assertTrue(falsy('false'))
        self.assertTrue(falsy('no'))
        self.assertTrue(falsy(0))
        self.assertTrue(falsy('0'))
        self.assertFalse(falsy('True'))

    def test_normalise(self):
        input = {
            'an_integer': 1,
            'a_string': "foo",
            'a_list': [1, 2, {'3': 3}],
            'a_dict': {
                'a_nested_item': "bar"
            }
        }
        output = {
            'anInteger': 1,
            'aString': "foo",
            'aList': [1, 2, {'3': 3}],
            'aDict': {
                'aNestedItem': "bar"
            }
        }
        self.assertEqual(output, normalise(input))

    def test_denormalise(self):
        input = {
            'anInteger': 1,
            'aString': "foo",
            'aList': [1, 2, {'3': 3}],
            'aDict': {
                'aNestedItem': "bar"
            }
        }
        output = {
            'an_integer': 1,
            'a_string': "foo",
            'a_list': [1, 2, {'3': 3}],
            'a_dict': {
                'a_nested_item': "bar"
            }
        }
        self.assertEqual(output, denormalise(input))

    def test_simplify(self):
        date = datetime.date(2015, 1, 1)
        id_ = uuid.uuid4()
        input = {
            'a_string': "foo",
            'a_date': date,
            'a_uuid': id_,
            'a_list': [1, id_, {'3': date}],
            'a_dict': {
                'a_nested_item': "bar"
            }
        }
        output = {
            'a_string': "foo",
            'a_date': time.mktime(date.timetuple()),
            'a_uuid': str(id_),
            'a_list': [1, str(id_), {'3': time.mktime(date.timetuple())}],
            'a_dict': {
                'a_nested_item': "bar"
            }
        }
        self.assertEqual(output, simplify(input))

    def test_son(self):
        date = datetime.date(2015, 1, 1)
        id_ = uuid.uuid4()
        input = {
            'a_string': "foo",
            'a_date': date,
            'a_uuid': id_,
            'a_list': [1, id_, {'3': date}],
            'a_dict': {
                'a_nested_item': "bar"
            }
        }
        output = {
            'aString': "foo",
            'aDate': time.mktime(date.timetuple()),
            'aUuid': str(id_),
            'aList': [1, str(id_), {'3': time.mktime(date.timetuple())}],
            'aDict': {
                'aNestedItem': "bar"
            }
        }
        to_son = ToSon()
        self.assertEqual(output, to_son(input))

    def test_son_node(self):

        input = TestNode(
            id_col=uuid.uuid4(),
            int_col=1,
            bool_col=True,
            string_col="foo",
            float_col=0.5,
            date_col=datetime.date(2015, 1, 1)
        )
        input.parent = TestNode(int_col=2, string_col="bar")

        output = {
            'idCol': str(input.id_col),
            'intCol': 1,
            'boolCol': True,
            'stringCol': "foo",
            'floatCol': 0.5,
            'parent': {
                'intCol': 2,
                'stringCol': "bar"
            },
            'dateCol': time.mktime(input.date_col.timetuple()),
        }
        to_son = ToSon(omit=True)
        self.assertEqual(output, to_son(input))

        output = {
            'idCol': str(input.id_col),
            'intCol': 1,
            'boolCol': True,
            'floatCol': 0.5,
            'parent': {
                'stringCol': "bar"
            },
            'dateCol': time.mktime(input.date_col.timetuple()),
        }
        to_son = ToSon(exclude=[r'^/string_col', r'parent/int_col'], omit=True)
        self.assertEqual(output, to_son(input))

        output = {
            'idCol': str(input.id_col),
            'parent': {
                'stringCol': "bar"
            }
        }
        to_son = ToSon(include=[r'^/id_col', r'^/parent$', r'parent/string_col'])
        self.assertEqual(output, to_son(input))

        output = {
            'idCol': str(input.id_col),
            'parent': {
                'intCol': 2,
            }
        }
        to_son = ToSon(
            include=[r'^/id_col', r'^/parent'],
            exclude=[r'string_col'],
            omit=True)
        self.assertEqual(output, to_son(input))

        input.parent.parent = input
        to_son = ToSon()
        with self.assertRaises(UtilException):
            to_son(input)
