import configparser
from db_requests import Database

db_path = ""  # Путь до БД
pause_hotkey = "f12"  # Установки/снятия паузы
pause_after_trade_hotkey = "ctrl+f12"  # Пауза, но с ожиданием завершения текущей торговли
close_hotkey = "f11"  # Мгновенное завершение
close_after_trade_hotkey = "ctrl+f11"  # Завершение программы, но с ожиданием завершения текущей торговли
db: Database


def upload_config():
    config = configparser.ConfigParser()
    config.read('config.ini')

    global db_path, pause_hotkey, pause_after_trade_hotkey, close_hotkey, close_after_trade_hotkey, db

    db_path = config['common']['db_path']
    pause_hotkey = config['common']['pause_hotkey']
    pause_after_trade_hotkey = config['common']['pause_after_trade_hotkey']
    close_hotkey = config['common']['close_hotkey']
    close_after_trade_hotkey = config['common']['close_after_trade_hotkey']
    db = Database()

