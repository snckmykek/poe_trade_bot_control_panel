import sqlite3
import gv

from kivymd.app import MDApp


class Database(object):

    def __init__(self):
        self.con = sqlite3.connect(fr'{gv.db_path}\database.db')
        self.con.row_factory = sqlite3.Row
        self.cur = self.con.cursor()
        self.sqlite_create_db()
        self.initial_setup()

    def commit(self):
        self.con.commit()

    def sqlite_create_db(self):
        # Настройки
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings(
                key TEXT NOT NULL PRIMARY KEY ON CONFLICT REPLACE,
                value NOT NULL,
                type TEXT NOT NULL
            ) 
            """)

        # Списки значений
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS limited_values(
                key TEXT NOT NULL,
                value NOT NULL,
                CONSTRAINT pk PRIMARY KEY (key, value)
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

    def save_settings(self, values):

        self.cur.execute(
            f"""
            INSERT INTO
                settings
            VALUES
                {','.join(map(str, values))}
            """
        )
        self.commit()

    def get_settings(self):
        self.cur.execute(
            """
            SELECT 
                *
            FROM
                settings
            """)

        return self.cur.fetchall()
