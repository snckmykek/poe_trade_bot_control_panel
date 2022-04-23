import sqlite3
from datetime import datetime

from kivymd.app import MDApp
f=1

class Database(object):

    def __init__(self):
        self.con = sqlite3.connect('database.db')
        self.con.row_factory = sqlite3.Row
        self.cur = self.con.cursor()
        self.sqlite_create_db()
        self.initial_setup()

    def commit(self):
        self.con.commit()

    def sqlite_create_db(self):
        # Карты (алгоритмы). Основное что-то, что движет логикой
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS maps(
                map TEXT NOT NULL PRIMARY KEY
            ) 
            """)

        # Настройки
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings(
                key TEXT NOT NULL PRIMARY KEY,
                value TEXT NOT NULL
            ) 
            """)

        # Настройки карты
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS map_settings(
                key TEXT NOT NULL PRIMARY KEY,
                value TEXT NOT NULL,
                frequency FLOAT DEFAULT 0,
                active BOOL NOT NULL DEFAULT False,
                type TEXT NOT NULL
            ) 
            """)

        # Скрипты для повторяющихся дествий
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS repetitive_actions(
                key INTEGER PRIMARY KEY AUTOINCREMENT,
                map TEXT NOT NULL,
                name TEXT NOT NULL,
                frequency FLOAT DEFAULT 0,
                active BOOL NOT NULL DEFAULT False,
                script TEXT DEFAULT ""
            ) 
            """)

    def initial_setup(self):
        self.fill_default()

        self.commit()

    def fill_default(self):
        # self.cur.execute(
        #     """
        #     INSERT OR IGNORE INTO
        #         limited_values
        #     VALUES
        #         ("lang", "ru"),
        #         ("lang", "en")
        #     """)
        pass

    def get_maps(self):
        request = f"""
                SELECT
                    maps.map
                FROM
                    maps
                """

        self.cur.execute(request)

        return [row[0] for row in self.cur.fetchall()]

    def add_map(self, map_name):
        self.cur.execute(
            f"""
            INSERT OR IGNORE INTO
                maps
            VALUES
                ("{map_name}")
            """)
        self.commit()

    def set_setting(self, key, val):

        self.cur.execute(
            f"""
            INSERT OR REPLACE INTO
                settings
            VALUES
                ("{key}", "{val}")
            """)

        self.commit()

    def get_setting(self, key):
        """Возвращает настройку по ключу.
        Если настройка не найдена, возвращает None.
        """

        self.cur.execute(
            f"""
            SELECT
                value
            FROM
                settings
            WHERE
                key = "{key}"
            """)

        try:
            return self.cur.fetchone()["value"]
        except TypeError:
            return None

    def set_rep_act(self, key, name="", frequency=0, active=False, script=""):

        self.cur.execute("""
                INSERT OR REPLACE INTO
                    repetitive_actions""" + ("" if key else " (map, name, frequency, active, script)") + """
                VALUES
                    (""" + (
            f"{key} ," if key else "") + f""""{MDApp.get_running_app().current_map}", "{name}", {frequency}, {active}, "{script}") 
                """)
        self.commit()

    def get_rep_acts(self):
        request = f"""
                SELECT
                    repetitive_actions.key,
                    repetitive_actions.name,
                    repetitive_actions.frequency,
                    repetitive_actions.active,
                    repetitive_actions.script
                FROM
                    repetitive_actions
                WHERE
                    repetitive_actions.map = "{MDApp.get_running_app().current_map}"
                """

        self.cur.execute(request)

        return self.cur.fetchall()

    def get_rep_act(self, key):
        request = f"""
                SELECT
                    repetitive_actions.name,
                    repetitive_actions.frequency,
                    repetitive_actions.active,
                    repetitive_actions.script
                FROM
                    repetitive_actions
                WHERE
                    repetitive_actions.map = "{MDApp.get_running_app().current_map}"
                    AND repetitive_actions.key = "{key}"
                """

        self.cur.execute(request)

        return self.cur.fetchone()

    def del_rep_act(self, key):
        self.cur.execute(f"""
            DELETE FROM repetitive_actions
            WHERE key = {key}"""
                         )
        self.commit()


db = Database()
