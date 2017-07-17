__all__ = ['Password']

from passlib.hash import sha256_crypt
from sqlalchemy import event
from sqlalchemy.types import TypeDecorator, Text


HASH_ROUNDS = 535000


class Password(TypeDecorator):
    '''
    Hashes passwords and provides mechanism for validation.

    When using this type for a column, the resulting column must then be
    instrumented with the `instrument` method.
    '''

    impl = Text

    @property
    def python_type(self):
        return HashedPassword

    def process_bind_param(self, value, dialect):
        # import pudb; pudb.set_trace()
        if value is None:
            return value
        elif isinstance(value, HashedPassword):
            return str(value)
        else:
            raise PasswordError(
                "Password columns must be instrumented with "
                "password.instrument")

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            return HashedPassword.from_cyphertext(value)

    @staticmethod
    def instrument(mapper_attr):
        '''
        Sets up a listener to convert plaintext to HashedPassword on
        assignment.
        '''
        @event.listens_for(mapper_attr, 'set', retval=True)
        def receive_set(target, value, oldvalue, initiator):
            if value is None:
                return None
            password = HashedPassword.from_plaintext(value)
            return password


class HashedPassword:
    def __init__(self):
        self.cyphertext = None

    @classmethod
    def from_cyphertext(cls, cyphertext):
        password = cls()
        password.cyphertext = cyphertext
        return password

    @classmethod
    def from_plaintext(cls, plaintext):
        password = cls()
        password.cyphertext = sha256_crypt.hash(plaintext, rounds=HASH_ROUNDS)
        return password

    def __eq__(self, other):
        if hasattr(other, 'cyphertext'):
            return other.cyphertext == self.cyphertext
        elif isinstance(other, str):
            return sha256_crypt.verify(other, self.cyphertext)
        else:
            return False

    def __str__(self):
        return self.cyphertext


class PasswordError(Exception):
    pass
