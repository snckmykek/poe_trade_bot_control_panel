import sqlite3
import threading


class Database:

    def __init__(self, db_path):
        self.con = sqlite3.connect(db_path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.cur = self.con.cursor()
        self.sqlite_create_db()
        self.initial_setup()
        self.lock = threading.Lock()

    def commit(self):
        self.con.commit()

    def sqlite_create_db(self):
        # Настройки
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings(
                bot_key NOT NULL,
                key TEXT NOT NULL,
                value NOT NULL,
                type TEXT NOT NULL,
                CONSTRAINT pk PRIMARY KEY (bot_key, key) ON CONFLICT REPLACE
            ) 
            """)

        # Списки значений
        # self.cur.execute(
        #     """
        #     CREATE TABLE IF NOT EXISTS limited_values(
        #         key TEXT NOT NULL,
        #         value NOT NULL,
        #         CONSTRAINT pk PRIMARY KEY (key, value) ON CONFLICT REPLACE
        #     )
        #     """)

        # Переменные для задач Бота
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS bots_variables(
                bot_key TEXT NOT NULL,
                key TEXT NOT NULL,
                window_key TEXT NOT NULL DEFAULT "any",
                value TEXT NOT NULL,
                CONSTRAINT pk PRIMARY KEY (bot_key, window_key, key) ON CONFLICT REPLACE
            ) 
            """)

        # Логи
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS logs(
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_key TEXT NOT NULL,
                date INTEGER NOT NULL,
                level INTEGER NOT NULL,
                text TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT ""
            ) 
            """)

        # Статистика времени выполнения этапов
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS stages_lead_time(
                date INT NOT NULL PRIMARY KEY,
                stage TEXT NOT NULL,
                lead_time INT NOT NULL,
                completed BOOL NOT NULL
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

    # region Переменные для задач Бота
    def get_bots_variable(self, bot_key, key, window_key):

        with self.lock:
            self.cur.execute(
                f"""
                SELECT 
                    value
                FROM
                    bots_variables
                WHERE
                    bot_key = "{bot_key}" and window_key = "{window_key}" and key = "{key}"
                """)

            result = self.cur.fetchone()
            if result:
                return result['value']

    def save_bots_variable(self, values: list):

        self.cur.executemany(
            f"""
            INSERT INTO
                bots_variables
            VALUES
                (?,?,?,?)
            """,
            values
        )
        self.commit()

    # endregion

    # region Настройки

    def get_setting(self, bot_key, key):

        with self.lock:
            self.cur.execute(
                f"""
                SELECT 
                    value
                FROM
                    settings
                WHERE
                    bot_key = "{bot_key}" and key = "{key}"
                """)

            result = self.cur.fetchone()
            if result:
                return result['value']

    def get_settings(self, bot_key, keys):
        self.cur.execute(
            f"""
            SELECT 
                *
            FROM
                settings
            WHERE
                bot_key = "{bot_key}" and key in {keys}
            """)

        return self.cur.fetchall()

    def save_settings(self, values: list):

        self.cur.executemany(
            f"""
            INSERT INTO
                settings
            VALUES
                (?,?,?,?)
            """,
            values
        )
        self.commit()

    # endregion

    # region Логи

    def get_log(self, log_id):
        self.cur.execute(
            f"""
            SELECT 
                *
            FROM
                logs
            WHERE
                log_id = {log_id}"
            """)

        return self.cur.fetchone()

    def get_logs(self, bot_key, start_time, end_time):
        self.cur.execute(
            f"""
            SELECT 
                *
            FROM
                logs
            WHERE
                bot_key = "{bot_key}" and date >= {start_time} and date <= {end_time}
            """)

        return self.cur.fetchall()

    def save_log(self, values: tuple):
        self.cur.execute(
            """
            INSERT INTO
                logs (bot_key, date, level, text, details)
            VALUES
                (?,?,?,?,?)
            """,
            values
        )
        self.commit()

    def save_stage_lead_time(self, values: tuple):
        with self.lock:
            self.cur.execute(
                """
                INSERT INTO
                    stages_lead_time
                VALUES
                    (?,?,?,?)
                """,
                values
            )
            self.commit()

    # endregion
