import configparser
import logging

import psycopg2
from psycopg2.extras import RealDictCursor


class PostgresClient:
    def __init__(self, dbname, user, password, host, port):
        self.user = user
        self.password = password
        self.dbname = dbname
        self.host = host
        self.port = port

    def db_connection(self):
        logging.info(f'Performing connection to db...')
        self._db_connection = psycopg2.connect(dbname=self.dbname,
                                               user=self.user,
                                               password=self.password,
                                               host=self.host,
                                               port=self.port, cursor_factory=RealDictCursor)
        self.db_cursor = self._db_connection.cursor()
        return self.db_cursor

    def close_connection(self):
        self.db_cursor.close()
        self._db_connection.close()
