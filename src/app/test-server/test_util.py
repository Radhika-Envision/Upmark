import datetime
import itertools
import time
import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String

import base
import model
from model.guid import GUID
from utils import denormalise, truthy, falsy, UtilException, ToSon


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

    def __str__(self):
        return "TestNode(%d)" % self.int_col


class ConversionTest(base.LoggingTestCase):

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
        to_son = ToSon(r'!^/string_col', r'!parent/int_col', omit=True)
        self.assertEqual(output, to_son(input))

        output = {
            'idCol': str(input.id_col),
            'parent': {
                'stringCol': "bar"
            }
        }
        to_son = ToSon(r'^/id_col', r'^/parent$', r'parent/string_col')
        self.assertEqual(output, to_son(input))

        output = {
            'idCol': str(input.id_col),
            'parent': {
                'intCol': 2,
            }
        }
        to_son = ToSon(
            r'^/id_col',
            r'^/parent',
            r'!string_col',
            omit=True)
        self.assertEqual(output, to_son(input))

        input.parent.parent = input
        to_son = ToSon()
        with self.assertRaises(UtilException):
            to_son(input)

    def test_son_iter(self):

        input = TestNode(
            id_col=uuid.uuid4(),
            int_col=1,
            bool_col=True,
            string_col="foo",
            float_col=0.5,
            date_col=datetime.date(2015, 1, 1)
        )
        input.parent = TestNode(int_col=2, string_col="bar")
        input.parent.parent = TestNode(int_col=3, string_col="baz")

        output = {
            'intCol': 1,
            'stringCol': "foo",
            'parent': {
                'intCol': 2,
                'stringCol': "bar",
                'parent': {
                    'intCol': 3,
                    'stringCol': "baz"
                }
            }
        }
        outputs = [item for item in itertools.repeat(output, 3)]

        to_son = ToSon(
            # Fields to match in any visisted object
            r'/int_col$',
            r'/string_col$',
            # Descend into nested objects
            r'/[0-9]+$',
            r'/parent$',
            omit=True)

        # List iteration
        inputs = [item for item in itertools.repeat(input, 3)]
        self.assertEqual(outputs, to_son(inputs))

        # Generator iteration
        inputs = (item for item in itertools.repeat(input, 3))
        self.assertEqual(outputs, to_son(inputs))

    def test_son_sanitise(self):
        input = {
            'safe_html':
                '<script>foo</script> '
                '<a href="http://bar">bar</a> '
                '<a href="javascript:fn()">baz</a>',
            'strip_script': '<script>foo</script>',
            'strip_protocol':
                '<a href="http://bar">bar</a> '
                '<a href="javascript:fn()">baz</a>',
            'strip_click':
                '<span onclick="fn()">bar</span> '
                '<a onclick="fn()">baz</a>',
            'a_dict': {
                'strip_script': '<script>foo</script>',
            }
        }
        output = {
            'safeHtml':
                '<script>foo</script> '
                '<a href="http://bar">bar</a> '
                '<a href="javascript:fn()">baz</a>',
            'stripScript': 'foo',
            'stripProtocol': '<a href="http://bar">bar</a> <a>baz</a>',
            'stripClick': 'bar <a>baz</a>',
            'aDict': {
                'stripScript': 'foo',
            }
        }
        to_son = ToSon(r'/safe_html$', r'</strip.*$', r'^/a_dict$')
        self.assertEqual(output, to_son(input))
