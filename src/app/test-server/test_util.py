import datetime
import unittest
from unittest import mock

from utils import to_dict, simplify, normalise, denormalise, truthy, falsy
import unittest


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
        self.assertEquals(output, normalise(input))

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
        self.assertEquals(output, denormalise(input))

    def test_simplify(self):
        input = {
            'a_string': "foo",
            'a_date': datetime.date(2015, 1, 1),
            'aList': [1, 2, {'3': datetime.date(2015, 1, 1)}],
            'aDict': {
                'aNestedItem': "bar"
            }
        }
        output = {
            'a_string': "foo",
            'a_date': "foo",
            'a_list': [1, 2, {'3': 3}],
            'a_dict': {
                'a_nested_item': "bar"
            }
        }
        self.assertEquals(output, denormalise(input))
