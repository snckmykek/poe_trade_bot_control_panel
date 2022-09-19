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
                app_type NOT NULL,
                key TEXT NOT NULL,
                value NOT NULL,
                type TEXT NOT NULL,
                CONSTRAINT pk PRIMARY KEY (app_type, key) ON CONFLICT REPLACE
            ) 
            """)

        # Списки значений
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS limited_values(
                key TEXT NOT NULL,
                value NOT NULL,
                CONSTRAINT pk PRIMARY KEY (key, value) ON CONFLICT REPLACE
            ) 
            """)

        # Настройки шаблонов
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS template_settings(
                app_type NOT NULL,
                key TEXT NOT NULL,
                value NOT NULL,
                type TEXT NOT NULL,
                CONSTRAINT pk PRIMARY KEY (app_type, key) ON CONFLICT REPLACE
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

    def save_template_settings(self, values):

        app_type = values[0][0]

        self.cur.execute(
            f"""
            DELETE FROM
                template_settings
            WHERE
                app_type = "{app_type}"
            """
        )
        self.cur.execute(
            f"""
            INSERT INTO
                template_settings
            VALUES
                {','.join(map(str, values))}
            """
        )
        self.commit()

    def get_settings(self, app_type):
        self.cur.execute(
            f"""
            SELECT 
                *
            FROM
                settings
            WHERE
                app_type = "{app_type}"
            """)

        return self.cur.fetchall()

    def get_template_settings(self, app_type):
        self.cur.execute(
            f"""
            SELECT 
                *
            FROM
                template_settings
            WHERE
                app_type = "{app_type}"
            """)

        return self.cur.fetchall()

    def get_selection(self, selection):
        self.cur.execute(
            f"""
            SELECT 
                value
            FROM
                limited_values
            WHERE
               key = "{selection}"
            """)

        return [row['value'] for row in self.cur.fetchall()]

    def add_selection_value(self, selection, value):
        self.cur.execute(
            f"""
            INSERT INTO
                limited_values
            VALUES
                {selection, value}
            """
        )
        self.commit()

    def delete_selection_value(self, selection, value):
        self.cur.execute(
            f"""
            DELETE FROM
                limited_values
            WHERE
                key = "{selection}" and value = "{value}"
            """
        )
        self.commit()