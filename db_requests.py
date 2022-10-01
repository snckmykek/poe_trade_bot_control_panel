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

        # Переменные для Действий
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS action_variables(
                app_type NOT NULL,
                window_resolution NOT NULL,
                key TEXT NOT NULL,
                value NOT NULL,
                type TEXT NOT NULL,
                CONSTRAINT pk PRIMARY KEY (app_type, window_resolution, key) ON CONFLICT REPLACE
            ) 
            """)

        # Доп настройки: Предметы
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS af_items(
                app_type NOT NULL,
                item TEXT NOT NULL,
                use BOOL NOT NULL,
                max_price INT NOT NULL,
                bulk_price INT NOT NULL,
                qty INT NOT NULL,
                CONSTRAINT pk PRIMARY KEY (app_type, item) ON CONFLICT REPLACE
            ) 
            """)

        # Доп настройки: Все предметы ПОЕ
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS af_poe_items(
                category TEXT NOT NULL,
                item TEXT NOT NULL,
                name TEXT NOT NULL,
                image TEXT NOT NULL,
                CONSTRAINT pk PRIMARY KEY (category, item) ON CONFLICT REPLACE
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

    def af_save_items(self, values):

        try:
            app_type = values[0][0]
        except IndexError:
            return

        self.cur.execute(
            f"""
            DELETE FROM
                af_items
            WHERE
                app_type = "{app_type}"
            """
        )

        self.cur.execute(
            f"""
            INSERT INTO
                af_items
            VALUES
                {','.join(map(str, values))}
            """
        )
        self.commit()

    def af_save_poe_items(self, values):

        self.cur.execute(
            f"""
            DELETE FROM
                af_poe_items
            """
        )

        self.cur.execute(
            f"""
            INSERT INTO
                af_poe_items
            VALUES
                {','.join(map(str, values))}
            """
        )
        self.commit()

    def save_action_variables(self, values):

        app_type = values[0][0]

        self.cur.execute(
            f"""
            DELETE FROM
                action_variables
            WHERE
                app_type = "{app_type}"
                and window_resolution in (SELECT 
                                            value
                                          FROM 
                                            settings
                                          WHERE 
                                            app_type = "{app_type}" and key = "setting_checkbox_window_resolution")
            """
        )
        self.cur.execute(
            f"""
            INSERT INTO
                action_variables
            VALUES
                {','.join(map(str, values))}
            """
        )
        self.commit()

    def get_settings(self, app_type, keys=None):

        if isinstance(keys, str):
            key = keys
        elif len(keys) == 1:
            key = keys[0]
        else:
            key = None

        if key:
            self.cur.execute(
                f"""
                SELECT 
                    *
                FROM
                    settings
                WHERE
                    app_type = "{app_type}" and key = "{key}"
                """)
        elif keys:
            self.cur.execute(
                f"""
                SELECT 
                    *
                FROM
                    settings
                WHERE
                    app_type = "{app_type}" and key in {keys}
                """)
        else:
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

    def af_get_items(self, app_type, items=None):

        if items is None:
            item = None
        elif isinstance(items, str):
            item = items
        elif len(items) == 1:
            item = items[0]
        else:
            item = None

        if item:
            where = f'WHERE af_poe_items.item = "{item}"'
        elif items:
            where = f'WHERE af_poe_items.item in {tuple(items)}'
        else:
            where = f'WHERE af_items.item IS NOT NULL'

        self.cur.execute(
            f"""
            SELECT 
                af_poe_items.item,
                af_poe_items.name,
                af_poe_items.image,
                IFNULL(af_items.use, False) as use,
                IFNULL(af_items.max_price, 0) as max_price,
                IFNULL(af_items.bulk_price, 0) as bulk_price,
                IFNULL(af_items.qty, 0) as qty
            FROM
                af_poe_items
                LEFT JOIN af_items
                    ON af_poe_items.item = af_items.item
                    AND af_items.app_type = "{app_type}"
            {where}
            """)

        return self.cur.fetchall()

    def af_get_categories(self):

        self.cur.execute(
            f"""
            SELECT DISTINCT 
                category
            FROM
                af_poe_items
            """)

        return self.cur.fetchall()

    def af_get_poe_items(self, category=None, search=None):

        where = ""
        if category:
            where += f"WHERE category = '{category}'"
        if search:
            search = "%" + "%".join(search.split(" ")) + "%"

            if where:
                where += f" AND name LIKE '{search}'"
            else:
                where += f"WHERE name LIKE '{search}'"

        self.cur.execute(
            f"""
            SELECT 
                *
            FROM
                af_poe_items
            {where}
            """)

        return self.cur.fetchall()

    def get_action_variables(self, app_type):
        self.cur.execute(
            f"""
            SELECT 
                *
            FROM
                action_variables
            WHERE
                app_type = "{app_type}"
                and window_resolution in (SELECT 
                                            value
                                          FROM 
                                            settings
                                          WHERE 
                                            app_type = "{app_type}" and key = "setting_checkbox_window_resolution")
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
