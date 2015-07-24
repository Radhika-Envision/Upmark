import datetime
import sys
import unittest
from unittest import mock

from dateutil.parser import parse

sys.path.append('.')

import watchdog


def get_config():
    return {
        'MINIMUM_UPTIME_MS': 60000,
        'MESSAGE_SUBJECT_TEST': "Test message",
        'MESSAGE_CONTENT_TEST': "Test message body",
        'MESSAGE_SUBJECT_CRASHED': "CRASH message",
        'MESSAGE_CONTENT_CRASHED': "Server ${server} crashed",
        'MESSAGE_SUBJECT_RECOVERED': "RECOVERED message",
        'MESSAGE_CONTENT_RECOVERED': "Server ${server} recovered",
        'MESSAGE_SEND_FROM': "joe",
        'MESSAGE_SEND_TO': "fred"
    }


class WatchdogTest(unittest.TestCase):

    def setUp(self):
        self.base_date = parse("2015-07-17T06:41:43.156012281Z")

    def test_config_missing(self):
        def get_config():
            raise FileNotFoundError()

        with mock.patch('watchdog.get_config', get_config), \
                self.assertRaises(SystemExit):
            watchdog.run([])

    def test_test_email(self):
        def _send(msg):
            self.assertEqual(msg['Subject'], "Test message")

        with mock.patch('watchdog._send', _send), \
                mock.patch('watchdog.get_config', get_config):
            watchdog.send_email('test', None)

    def test_initial(self):
        def get_container_info():
            started_at = self.base_date
            running = True
            return started_at, running

        def load_state():
            return {}

        def save_state(state):
            self.assertEqual(state['status'], 'running')
            self.assertEqual(state['started_at'], self.base_date)

        def _send(msg):
            raise ValueError()

        with mock.patch('watchdog.get_container_info', get_container_info), \
                mock.patch('watchdog.load_state', load_state), \
                mock.patch('watchdog.save_state', save_state), \
                mock.patch('watchdog.get_config', get_config), \
                mock.patch('watchdog._send', _send):
            watchdog.check_docker()

    def test_running_running(self):
        def get_container_info():
            started_at = self.base_date
            running = True
            return started_at, running

        def load_state():
            return {
                'status': 'running',
                'started_at': self.base_date
            }

        def save_state(state):
            self.assertEqual(state['status'], 'running')
            self.assertEqual(
                state['started_at'], self.base_date)

        def _send(msg):
            raise ValueError()

        with mock.patch('watchdog.get_container_info', get_container_info), \
                mock.patch('watchdog.load_state', load_state), \
                mock.patch('watchdog.save_state', save_state), \
                mock.patch('watchdog.get_config', get_config), \
                mock.patch('watchdog._send', _send):
            watchdog.check_docker()

    def test_running_crashed(self):
        def gethostname():
            return "Foo"

        def get_container_info():
            started_at = self.base_date + datetime.timedelta(days=1)
            running = True
            return started_at, running

        def load_state():
            return {
                'status': 'running',
                'started_at': self.base_date
            }

        def save_state(state):
            self.assertEqual(state['status'], 'crashed')
            self.assertEqual(
                state['started_at'], self.base_date + datetime.timedelta(days=1))

        def _send(msg):
            self.assertEqual(msg['Subject'], "CRASH message")
            self.assertEqual(msg.get_payload(), "Server Foo crashed")

        with mock.patch('watchdog.get_container_info', get_container_info), \
                mock.patch('watchdog.load_state', load_state), \
                mock.patch('watchdog.save_state', save_state), \
                mock.patch('watchdog.get_config', get_config), \
                mock.patch('watchdog._send', _send), \
                mock.patch('socket.gethostname', gethostname):
            watchdog.check_docker()

    def test_crashed_crashed_starting_up(self):
        def get_container_info():
            started_at = self.base_date + datetime.timedelta(seconds=10)
            running = True
            return started_at, running

        def load_state():
            return {
                'status': 'crashed',
                'started_at': self.base_date
            }

        def save_state(state):
            self.assertEqual(state['status'], 'crashed')
            self.assertEqual(state['started_at'], self.base_date)

        def _send(msg):
            raise ValueError()

        with mock.patch('watchdog.get_container_info', get_container_info), \
                mock.patch('watchdog.load_state', load_state), \
                mock.patch('watchdog.save_state', save_state), \
                mock.patch('watchdog.get_config', get_config), \
                mock.patch('watchdog._send', _send):
            watchdog.check_docker()

    def test_crashed_crashed_still_crashing(self):
        def get_container_info():
            started_at = self.base_date + datetime.timedelta(days=1)
            running = False
            return started_at, running

        def load_state():
            return {
                'status': 'crashed',
                'started_at': self.base_date
            }

        def save_state(state):
            self.assertEqual(state['status'], 'crashed')
            self.assertEqual(state['started_at'], self.base_date)

        def _send(msg):
            raise ValueError()

        with mock.patch('watchdog.get_container_info', get_container_info), \
                mock.patch('watchdog.load_state', load_state), \
                mock.patch('watchdog.save_state', save_state), \
                mock.patch('watchdog.get_config', get_config), \
                mock.patch('watchdog._send', _send):
            watchdog.check_docker()

    def test_crashed_running(self):
        def gethostname():
            return "Foo"

        def get_container_info():
            started_at = self.base_date + datetime.timedelta(minutes=2)
            running = True
            return started_at, running

        def load_state():
            return {
                'status': 'crashed',
                'started_at': self.base_date
            }

        def save_state(state):
            self.assertEqual(state['status'], 'running')
            self.assertEqual(
                state['started_at'], self.base_date + datetime.timedelta(minutes=2))

        def _send(msg):
            self.assertEqual(msg['Subject'], "RECOVERED message")
            self.assertEqual(msg.get_payload(), "Server Foo recovered")

        with mock.patch('watchdog.get_container_info', get_container_info), \
                mock.patch('watchdog.load_state', load_state), \
                mock.patch('watchdog.save_state', save_state), \
                mock.patch('watchdog.get_config', get_config), \
                mock.patch('watchdog._send', _send), \
                mock.patch('socket.gethostname', gethostname):
            watchdog.check_docker()
