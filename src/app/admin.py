#!/usr/bin/env python3

import argparse
import getpass
import os
import sys

try:
    import sqlalchemy
except ImportError:
    print('Failed to load sqlalchemy. Do you need to enter a virtual environment?')

from server.model import AppUser, connect_db, session_scope, Utility


def add_user(args):
    connect_db(os.environ.get('DATABASE_URL'))
    password = getpass.getpass()
    try:
        with session_scope() as session:
            user = AppUser(user_id=args.email, name=args.name, role=args.role)
            user.set_password(password)
            if args.utility is not None:
                utility = session.query(Utility) \
                    .filter_by(name=args.utility).one()
                user.utility_id = utility.id
            session.add(user)
    except sqlalchemy.exc.IntegrityError as e:
        print('Failed to add user %s' % args.name)
        print('\n'.join(e.orig.args))
        sys.exit(1)
    print('Added user %s' % args.name)


def default_command(args):
    print('Default command')


def run(argv):
    parser = argparse.ArgumentParser()
    #parser.add_argument('--foo', type=float)
    subparsers = parser.add_subparsers()

    subparser = subparsers.add_parser('adduser')
    subparser.add_argument('email')
    subparser.add_argument('name')
    subparser.add_argument('role', default='clerk')
    subparser.add_argument('--utility')
    subparser.set_defaults(func=add_user)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    run(None)
