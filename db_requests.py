import sqlite3
import glob

from kivymd.app import MDApp


class Database(object):

    def __init__(self):
        self.con = sqlite3.connect(fr'{glob.db_path}\database.db')
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
                key TEXT NOT NULL PRIMARY KEY,
                value NOT NULL
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

    def test(self):
        self.cur.execute(
            """
            INSERT INTO
                settings
            VALUES
                ("test", 1)
            ON CONFLICT(key) DO UPDATE SET value = value + 1
            """)
        self.commit()

    def test_read(self):
        self.cur.execute(
            """
            SELECT 
                *
            FROM
                settings
            """)

        return self.cur.fetchone()[1]
