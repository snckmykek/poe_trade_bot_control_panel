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
        # Инфа по ячейкам стеша
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cells_info(
                tab_type TEXT NOT NULL,
                cell_id TEXT NOT NULL,
                section TEXT NOT NULL,
                x FLOAT NOT NULL,
                y FLOAT NOT NULL,
                CONSTRAINT pk PRIMARY KEY (tab_number, cell_id) ON CONFLICT REPLACE
            ) 
            """)

        # Инфа по вкладкам стеша
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tabs_info(
                tab_number TEXT NOT NULL PRIMARY KEY ON CONFLICT REPLACE,
                use BOOL NOT NULL,
                tab_name TEXT NOT NULL,
                tab_layout TEXT NOT NULL,
                sections TEXT NOT NULL
            ) 
            """)

        # Предметы
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS items(
                tab_number TEXT NOT NULL,
                tab_name TEXT NOT NULL,
                cell_id TEXT NOT NULL,
                is_layout BOOL NOT NULL,
                item TEXT NOT NULL,
                item_name TEXT NOT NULL,
                typeLine TEXT NOT NULL,
                baseType TEXT NOT NULL,
                w INTEGER NOT NULL,
                h INTEGER NOT NULL,
                icon TEXT NOT NULL,
                qty INTEGER NOT NULL,
                stack_size INTEGER NOT NULL,
                min_qty INTEGER NOT NULL,
                price_for_min_qty INTEGER NOT NULL,
                currency TEXT NOT NULL,
                identified BOOL NOT NULL,
                ilvl INTEGER NOT NULL,
                note TEXT NOT NULL,
                CONSTRAINT pk PRIMARY KEY (tab_number, cell_id) ON CONFLICT REPLACE
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

    def clear_cells_info(self):
        self.cur.execute(
            """
            DELETE FROM
                cells_info
            """
        )
        self.commit()

    def get_cells_info(self, tab_layout, section):

        self.cur.execute(
            f"""
            SELECT
                cell_id
                ,x
                ,y
            FROM
                cells_info
            WHERE
                tab_type = ? and section = ?
            ORDER BY y, x
            """,
            [tab_layout, section]
        )

        result = self.cur.fetchall()

        return result

    def save_cells_info(self, values):
        self.cur.executemany(
            """
            INSERT INTO
                cells_info
            VALUES
                (?,?,?,?,?,?)
            """,
            values
        )
        self.commit()

    def clear_items(self):
        self.cur.execute(
            """
            DELETE FROM
                items
            """
        )
        self.commit()

    def save_items(self, values):
        self.cur.executemany(
            """
            INSERT INTO
                items
            VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            values
        )
        self.commit()

    def get_item_info(self, item_name, position):
        if position is not None:
            tab_name = position['tab']
            cell_id = ",".join(map(str, [position['col'], position['row']]))
        else:
            tab_name = ""
            cell_id = ""

        self.cur.execute(
            f"""
            SELECT
                CAST(items.tab_number as INT) as tab_number
                ,items.cell_id
                ,items.is_layout
                ,items.item
                ,items.item_name
                ,items.typeLine
                ,items.baseType
                ,items.w
                ,items.h
                ,items.icon
                ,items.qty
                ,items.stack_size
                ,items.min_qty
                ,items.price_for_min_qty
                ,items.currency
                ,items.identified
                ,items.ilvl
                ,items.note
                ,IFNULL(cells_info.tab_type, "") as tab_type
                ,IFNULL(cells_info.section, "") as section
                ,IFNULL(cells_info.x, 0) as x
                ,IFNULL(cells_info.y, 0) as y
            FROM
                items
                LEFT JOIN 
                    cells_info
                ON 
                    items.tab_number = cells_info.tab_number
                    AND items.cell_id = cells_info.cell_id
            WHERE
                (items.item_name = ? AND items.is_layout)
                OR (items.item_name = ? AND items.tab_name = ? AND items.cell_id = ?)
            """,
            [item_name, item_name, tab_name, cell_id]
        )
        return self.cur.fetchone()

    def get_items_qty(self, items: list):

        self.cur.execute(
            f"""
            SELECT
                items.item_name
                ,items.qty
            FROM
                items
            WHERE
                (items.item_name IN({",".join("?" * len(items))}) AND items.is_layout)
            """,
            items
        )

        result = {}
        for row in self.cur.fetchall():
            result.update({row['item_name']: row['qty']})

        return result

    def change_item_qty(self, item_name, qty, position):

        if position is not None:
            condition = "AND tab_number = ? AND cell_id = ?"
            values = [qty, item_name, position['tab'], ",".join(map(str, [position['col'], position['row']]))]
        else:
            condition = ""
            values = [qty, item_name]

        self.cur.execute(
            f"""
            UPDATE
                items
            SET
                qty = qty + ?
            WHERE
                item_name = ?
                {condition}
            """,
            values
        )

        self.commit()

    def get_tabs_layouts(self):

        self.cur.execute(
            f"""
            SELECT DISTINCT
                tab_type as tab_layout
                ,section
            FROM
                cells_info
            """
        )

        result = {'common': []}
        for row in self.cur.fetchall():
            try:
                result[row['tab_layout']].append(row['section'])
            except KeyError:
                result.update({row['tab_layout']: [row['section'], ]})

        return result

    def get_tabs_info(self):
        self.cur.execute(
            f"""
            SELECT
                tab_number
                ,use
                ,tab_name
                ,tab_layout
                ,sections
            FROM
                tabs_info
            """
        )

        result = self.cur.fetchall()

        return result

    def save_tabs_info(self, values):
        self.cur.execute(
            """
            DELETE FROM
                tabs_info
            """
        )
        self.cur.executemany(
            """
            INSERT INTO
                tabs_info
            VALUES
                (?,?,?,?,?)
            """,
            values
        )
        self.commit()
