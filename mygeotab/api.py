# -*- coding: utf-8 -*-

from __future__ import unicode_literals

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

try:
    import ujson as json
except ImportError:
    import json

import requests
requests.packages.urllib3.disable_warnings()


class API(object):
    _reauthorize_count = 0

    def __init__(self, username, password=None, database=None, session_id=None, server='my.geotab.com'):
        """
        Creates a new instance of this simple Pythonic wrapper for the MyGeotab API.

        :param username: The username used for MyGeotab servers. Usually an email address.
        :param password: The password associated with the username. Optional if `session_id` is provided.
        :param database: The database or company name. Optional as this usually gets resolved upon authentication.
        :param session_id: A session ID, assigned by the server.
        :param server: The server ie. my23.geotab.com. Optional as this usually gets resolved upon authentication.
        :raise Exception: Raises an Exception if a username, or one of the session_id or password is not provided.
        """
        if username is None:
            raise Exception('`username` cannot be None')
        if password is None and session_id is None:
            raise Exception('`password` and `session_id` must not both be None')
        self.credentials = Credentials(username, session_id, database, server, password)

    @staticmethod
    def from_credentials(credentials):
        """
        Returns a new API object from an existing Credentials object

        :param credentials: The existing saved credentials
        :return: A new API object populated with MyGeotab credentials
        """
        return API(username=credentials.username, password=credentials.password, database=credentials.database,
                   session_id=credentials.session_id, server=credentials.server)

    def _get_api_url(self):
        """
        Formats the server URL properly in order to query the API.

        :rtype: str
        :return: A valid MyGeotab API request URL
        """
        if not self.credentials.server:
            self.credentials.server = 'my.geotab.com'
        parsed = urlparse(self.credentials.server)
        base_url = parsed.netloc if parsed.netloc else parsed.path
        base_url.replace('/', '')
        return 'https://' + base_url + '/apiv1'

    def _query(self, method, parameters):
        """
        Formats and performs the query against the API

        :param method: The method name.
        :param parameters: A dict of parameters to send
        :return: The JSON-decoded result from the server
        :raise MyGeotabException: Raises when an exception occurs on the MyGeotab server
        """
        params = dict(id=-1, method=method, params=parameters)
        headers = {'Content-type': 'application/json; charset=UTF-8'}
        url = self._get_api_url()
        is_live = not any(s in url for s in ['127.0.0.1', 'localhost'])
        r = requests.post(url, data=json.dumps(params), headers=headers, allow_redirects=True, verify=is_live)
        data = r.json()
        if data:
            if 'error' in data:
                raise MyGeotabException(data['error'])
            if 'result' in data:
                return data['result']
            return data
        return None

    def call(self, method, type_name=None, **parameters):
        """
        Makes a call to the API.

        :param method: The method name.
        :param type_name: The type of entity for generic methods (for example, 'Get')
        :param parameters: Additional parameters to send (for example, search=dict(id='b123') )
        :return: The JSON result (decoded into a dict) from the server
        :raise MyGeotabException: Raises when an exception occurs on the MyGeotab server
        """
        if method is None:
            raise Exception("Must specify a method name")
        if parameters is None:
            parameters = {}
        if type_name:
            parameters['typeName'] = type_name
        if self.credentials is None:
            self.authenticate()
        if not 'credentials' in parameters and self.credentials.session_id:
            parameters['credentials'] = self.credentials.get_param()

        try:
            result = self._query(method, parameters)
            if result is not None:
                self._reauthorize_count = 0
                return result
        except MyGeotabException as exception:
            if exception.name == 'InvalidUserException' and self._reauthorize_count == 0:
                self._reauthorize_count += 1
                self.authenticate()
                return self.call(method, parameters)
            raise
        return None

    def multi_call(self, *calls):
        """
        Performs a multi-call to the API
        :param calls: A list of call 2-tuples with method name and params (for example, ('Get', dict(typeName='Trip')) )
        :return: The JSON result (decoded into a dict) from the server
        :raise MyGeotabException: Raises when an exception occurs on the MyGeotab server
        """
        formatted_calls = [dict(method=call[0], params=call[1]) for call in calls]
        return self.call('ExecuteMultiCall', calls=formatted_calls)

    def get(self, type_name, **parameters):
        """
        Gets entities using the API. Shortcut for using call() with the 'Get' method.

        :param type_name: The type of entity
        :param parameters: Additional parameters to send.
        :return: The JSON result (decoded into a dict) from the server
        :raise MyGeotabException: Raises when an exception occurs on the MyGeotab server
        """
        return self.call('Get', type_name, **parameters)

    def add(self, type_name, entity):
        """
        Adds an entity using the API. Shortcut for using call() with the 'Add' method.

        :param type_name: The type of entity
        :param entity: The entity to add
        :return: The id of the object added
        :raise MyGeotabException: Raises when an exception occurs on the MyGeotab server
        """
        return self.call('Add', type_name, entity=entity)

    def set(self, type_name, entity):
        """
        Sets an entity using the API. Shortcut for using call() with the 'Set' method.

        :param type_name: The type of entity
        :param entity: The entity to set
        :raise MyGeotabException: Raises when an exception occurs on the MyGeotab server
        """
        return self.call('Set', type_name, entity=entity)

    def remove(self, type_name, entity):
        """
        Removes an entity using the API. Shortcut for using call() with the 'Remove' method.

        :param type_name: The type of entity
        :param entity: The entity to remove
        :raise MyGeotabException: Raises when an exception occurs on the MyGeotab server
        """
        return self.call('Remove', type_name, entity=entity)

    def authenticate(self):
        """
        Authenticates against the API server.

        :return: A Credentials object with a session ID created by the server
        :raise AuthenticationException: Raises if there was an issue with authenticating or logging in
        :raise MyGeotabException: Raises when an exception occurs on the MyGeotab server
        """
        auth_data = dict(database=self.credentials.database, userName=self.credentials.username,
                         password=self.credentials.password)
        auth_data['global'] = True
        try:
            result = self._query('Authenticate', auth_data)
            if result:
                new_server = result['path']
                server = self.credentials.server
                if new_server != 'ThisServer':
                    server = new_server
                c = result['credentials']
                self.credentials = Credentials(c['userName'], c['sessionId'], c['database'], server)
                return self.credentials
        except MyGeotabException as exception:
            if exception.name == 'InvalidUserException':
                raise AuthenticationException(self.credentials.username, self.credentials.database,
                                              self.credentials.server)
            raise


class Credentials(object):
    def __init__(self, username, session_id, database, server, password=None):
        """
        Creates a new instance of a MyGeotab credentials object

        :param username: The username used for MyGeotab servers. Usually an email address.
        :param session_id: A session ID, assigned by the server.
        :param database: The database or company name. Optional as this usually gets resolved upon authentication.
        :param server: The server ie. my23.geotab.com. Optional as this usually gets resolved upon authentication.
        :param password: The password associated with the username. Optional if `session_id` is provided.
        """
        self.username = username
        self.session_id = session_id
        self.database = database
        self.server = server
        self.password = password

    def __str__(self):
        return '{0} @ {1}/{2}'.format(self.username, self.server, self.database)

    def get_param(self):
        """
        A simple representation of the credentials object for passing into the API.authenticate() server call

        :return: The simple credentials object for use by API.authenticate()
        """
        return dict(userName=self.username, sessionId=self.session_id, database=self.database)


class MyGeotabException(Exception):
    def __init__(self, full_error):
        """
        Creates a Pythonic exception for server-side exceptions

        :param full_error: The full JSON-decoded error
        """
        self._full_error = full_error
        main_error = full_error['errors'][0]
        self.name = main_error['name']
        self.message = main_error['message']
        self.stack_trace = main_error['stackTrace']

    def __str__(self):
        return '{0}\n{1}\n\nStacktrace:\n{2}'.format(self.name, self.message, self.stack_trace)


class AuthenticationException(Exception):
    def __init__(self, username, database, server):
        """
        An exception raised on an unsuccessful authentication with the server

        :param username: The username used for MyGeotab servers. Usually an email address.
        :param database: The database or company name.
        :param server: The server ie. my23.geotab.com.
        """
        self.username = username
        self.database = database
        self.server = server

    def __str__(self):
        return 'Cannot authenticate \'{0} @ {1}/{2}\''.format(self.username, self.server, self.database)