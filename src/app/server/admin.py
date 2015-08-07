#!/usr/bin/env python3

import argparse
import getpass
import os
import sys

try:
    import sqlalchemy
    import sqlalchemy.orm.exc
except ImportError:
    print('Failed to load sqlalchemy. Do you need to enter a virtual environment?')

from model import AppUser, connect_db, session_scope, Organisation


def modify_user(args):
    connect_db(os.environ.get('DATABASE_URL'))

    password = getpass.getpass(prompt='Enter new password: ')
    password2 = getpass.getpass(prompt='Re-enter password: ')
    if password != password2:
        print('Failed to add user %s' % args.name)
        print('Passwords do not match')
        sys.exit(1)

    try:
        with session_scope() as session:
            if args.organisation is not None:
                organisation = session.query(Organisation) \
                    .filter_by(name=args.organisation).one()
            else:
                organisation = None

            try:
                user = session.query(AppUser).filter_by(email=args.email).one()
                is_new = False
                if password != "":
                    user.set_password(password)
            except sqlalchemy.orm.exc.NoResultFound:
                is_new = True
                user = AppUser(email=args.email)
                session.add(user)
                if password != "":
                    user.set_password(password)
                else:
                    print("Not setting a password. User will not be able to log in.")
                    user.password = "!"

            if args.name is not None:
                user.name = args.name
            if args.role is not None:
                user.role = args.role
            if organisation is not None:
                user.organisation_id = str(organisation.id)
            session.flush()
            session.expunge(user)

    except sqlalchemy.exc.IntegrityError as e:
        print('Failed to add user %s' % args.email)
        print('\n'.join(e.orig.args))
        sys.exit(1)

    if is_new:
        print('Added user %s' % user.email)
    else:
        print('Updated user %s' % user.email)
    print('ID: %s' % user.id)


def modify_org(args):
    connect_db(os.environ.get('DATABASE_URL'))

    try:
        with session_scope() as session:
            try:
                org = session.query(Organisation).filter_by(name=args.name).one()
                is_new = True
            except sqlalchemy.orm.exc.NoResultFound:
                is_new = False
                org = Organisation(name=args.name)
                session.add(org)

            if args.region is not None:
                org.region = args.region
            if args.url is not None:
                org.url = args.url
            if args.customers is not None:
                org.number_of_customers = args.customers

            session.flush()
            session.expunge(org)

    except sqlalchemy.exc.IntegrityError as e:
        print('Failed to create organisation %s' % args.name)
        print('\n'.join(e.orig.args))
        sys.exit(1)

    if is_new:
        print('Added organisation %s' % org.name)
    else:
        print('Updated organisation %s' % org.name)
    print('ID: %s' % org.id)


def default_command(args):
    print('Default command')


def run(argv):
    parser = argparse.ArgumentParser()
    #parser.add_argument('--foo', type=float)
    subparsers = parser.add_subparsers()

    subparser = subparsers.add_parser('user')
    subparser.add_argument('email')
    subparser.add_argument('--name')
    subparser.add_argument('--role')
    subparser.add_argument('--organisation')
    subparser.set_defaults(func=modify_user)

    subparser = subparsers.add_parser('org')
    subparser.add_argument('name')
    subparser.add_argument('--region')
    subparser.add_argument('--url')
    subparser.add_argument('--customers', default=0)
    subparser.set_defaults(func=modify_org)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    run(None)
