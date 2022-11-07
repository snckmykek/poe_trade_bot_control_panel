import sqlite3


class Database:

    def __init__(self, db_path):
        self.con = sqlite3.connect(db_path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.cur = self.con.cursor()
        self.sqlite_create_db()
        self.initial_setup()

    def commit(self):
        self.con.commit()

    def sqlite_create_db(self):

        # Предметы
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS items(
                item TEXT PRIMARY KEY ON CONFLICT REPLACE,
                use BOOL NOT NULL,
                max_price REAL NOT NULL,
                bulk_price REAL NOT NULL,
                max_qty INT NOT NULL
            ) 
            """)

        # Все предметы ПОЕ
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS poe_items(
                category TEXT NOT NULL,
                item TEXT NOT NULL,
                name TEXT NOT NULL,
                image TEXT NOT NULL,
                CONSTRAINT pk PRIMARY KEY (category, item) ON CONFLICT REPLACE
            ) 
            """)

        # История сделок
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS deals_history(
                date INT NOT NULL PRIMARY KEY,
                completed BOOL NOT NULL,
                error TEXT DEFAULT "",
                item TEXT NOT NULL,
                qty INT NOT NULL,
                c_price REAL NOT NULL,
                profit REAL NOT NULL
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

    def save_items(self, values):

        self.cur.execute(
            f"""
            DELETE FROM
                items
            """
        )

        self.cur.execute(
            f"""
            INSERT INTO
                items
            VALUES
                {','.join(map(str, values))}
            """
        )
        self.commit()

    def save_poe_items(self, values):

        self.cur.execute(
            f"""
            DELETE FROM
                poe_items
            """
        )

        self.cur.execute(
            f"""
            INSERT INTO
                poe_items
            VALUES
                {','.join(map(str, values))}
            """
        )
        self.commit()

    def get_items(self, items=None):

        if items is None:
            item = None
        elif isinstance(items, str):
            item = items
        elif len(items) == 1:
            item = items[0]
        else:
            item = None

        if item:
            where = f'WHERE poe_items.item = "{item}"'
        elif items:
            where = f'WHERE poe_items.item in {tuple(items)}'
        else:
            where = f'WHERE items.item IS NOT NULL'

        self.cur.execute(
            f"""
            SELECT 
                poe_items.item,
                poe_items.name,
                poe_items.image,
                IFNULL(items.use, False) as use,
                IFNULL(items.max_price, 0) as max_price,
                IFNULL(items.bulk_price, 0) as bulk_price,
                IFNULL(items.max_qty, 0) as max_qty
            FROM
                poe_items
                LEFT JOIN items
                    ON poe_items.item = items.item
            {where}
            """)

        return self.cur.fetchall()

    def get_categories(self):

        self.cur.execute(
            f"""
            SELECT DISTINCT 
                category
            FROM
                poe_items
            """)

        return self.cur.fetchall()

    def get_poe_items(self, category=None, search=None):

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
                poe_items
            {where}
            """)

        return self.cur.fetchall()

    def get_poe_item_image(self, item):

        self.cur.execute(
            f"""
            SELECT 
                image
            FROM
                poe_items
            WHERE item = "{item}"
            """)

        return self.cur.fetchone()['image']
