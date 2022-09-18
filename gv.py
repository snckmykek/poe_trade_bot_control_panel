"""
global variables
"""

import configparser

from kivymd.app import MDApp

from db_requests import Database

db_path: str  # Путь до БД
is_executor: bool
db: Database


def upload_config():
    config = configparser.ConfigParser(inline_comment_prefixes="#")
    if not config.read('config.ini'):
        raise FileNotFoundError

    global db_path, db, is_executor

    db_path = config['common']['db_path']
    is_executor = config.getboolean('common', 'is_executor')
    db = Database()
