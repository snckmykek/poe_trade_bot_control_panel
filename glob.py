import configparser
from db_requests import Database

db_path = ""  # Путь до БД
hotkey_pause = "f11"  # Установки/снятия паузы (будет ждать завершения всех действий)
hotkey_stop_action = "f12"  # Остановка текущего действия
hotkey_close = "ctrl+f11"  # Мгновенное завершение
hotkey_close_after_actions = "ctrl+f12"  # Завершение программы, но с ожиданием завершения текущей торговли
db: Database


def upload_config():
    config = configparser.ConfigParser(inline_comment_prefixes="#")
    if not config.read('config.ini'):
        raise FileNotFoundError

    global db_path, hotkey_pause, hotkey_stop_action, hotkey_close, hotkey_close_after_actions, db

    db_path = config['common']['db_path']
    hotkey_pause = config['common']['hotkey_pause']
    hotkey_stop_action = config['common']['hotkey_stop_action']
    hotkey_close = config['common']['hotkey_close']
    hotkey_close_after_actions = config['common']['hotkey_close_after_actions']
    db = Database()
