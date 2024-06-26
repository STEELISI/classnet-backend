'''
Persistent users for the api.

Users are identified by (email, realm) pair which must be unique.
`pword` column stores a hashed password that is supplied during
user registration.
'''

import sys
import logging
from os.path import exists

from flask_sqlalchemy import (
    SQLAlchemy,
)
from sqlalchemy import exc

from flask_bcrypt import (
    generate_password_hash,
    check_password_hash,
)


_db = SQLAlchemy()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


class UserError(BaseException):
    '''Base class for exceptions generated by this module'''

class DBError(UserError):
    '''Errors related to db: integrity, lookup etc.'''

class User(_db.Model):
    '''SQLAlchemy class for access to user-table'''
    __table_args__ = (
        _db.Index(
            '_email_realm_dex',
            'email',
            'realm',
            unique=True
        ),
        #db.UniqueConstraint('email', 'realm', name='unique_email_realm'),
    )
    uid =   _db.Column(_db.Integer, primary_key = True)
    uname = _db.Column(_db.String, nullable=False)
    email = _db.Column(_db.String, nullable=False)
    realm = _db.Column(_db.String, nullable=False)
    pword = _db.Column(_db.String, nullable=False)

    def _save(self):
        '''save the user record in db, but hash the pword first'''
        self.pword = generate_password_hash(self.pword).decode('utf8')
        _db.session.add(self) #pylint:disable=no-member
        _db.session.commit()  #pylint:disable=no-member

    def check_pword(self, password):
        '''verify user-provided password against the hash stored in User/db'''
        return check_password_hash(self.pword, password)

    @classmethod
    def lookup(cls, email, realm):
        '''lookup email/realm'''
        return cls.query.filter_by(email=email, realm=realm).first()

    @classmethod
    def create(cls, **kwargs):
        '''create a new user'''
        try:
            user = cls(**kwargs)
            user._save()
        except exc.IntegrityError as ex:
            msg = 'Cannot create user: integrity error'
            LOG.error(msg)
            raise DBError(msg) from ex
        return user

    @classmethod
    def delete(cls, **kwargs):
        '''create a new user'''
        user = cls.lookup(kwargs['email'], kwargs['realm'])
        if user is None:
            raise DBError('user/realm are not registered')
        _db.session.delete(user) #pylint:disable=no-member
        _db.session.commit()     #pylint:disable=no-member

    @classmethod
    def list(cls):
        '''lookup email/realm'''
        all_users = cls.query.all()
        return [{'email': user.email, 'realm': user.realm} for user in all_users]


def init_db(app):
    '''Initialize users/db component'''
    _db.init_app(app)
    dbschema, dbfile = app.config['SQLALCHEMY_DATABASE_URI'].split(':///')
    assert dbschema == 'sqlite'
    if not exists('instance/' + dbfile):
        with app.app_context():
            _db.create_all()
    else:
        print(f'{dbfile} already exists, not re-creating', file=sys.stderr)


#add admin user
def initialize(app):
    '''Runs at istallation: creates database and adds an admin user'''

    print('initalizing database')
    init_db(app)
    #creates the database and adds admin user to it
    print('Adding a user to admin realm, instance_path:', app.instance_path)
    uname = input('Full Name : ')
    email = input('Email     : ')
    pword = input('Password  : ')
    if not uname or not email or not pword:
        LOG.error('the name, email and password must not be empty')
        sys.exit(1)
    try:
        with app.app_context():
            User.create(uname = uname, email = email, pword=pword, realm='admin')
    except Exception as ex: # pylint: disable=broad-except
        LOG.exception('Error adding admin user: %s', ex)
