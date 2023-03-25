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
                tab_number TEXT NOT NULL,
                tab_type TEXT NOT NULL,
                cell_id TEXT NOT NULL,
                section TEXT NOT NULL,
                x FLOAT NOT NULL,
                y FLOAT NOT NULL,
                CONSTRAINT pk PRIMARY KEY (tab_number, cell_id) ON CONFLICT REPLACE
            ) 
            """)

        # Предметы
        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS items(
                tab_number TEXT NOT NULL,
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
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            values
        )
        self.commit()

    def get_item_info(self, item_name, position):
        pos_condition = "AND items.tab_number = {} AND items.cell_id = {}".format(
            position['tab'], ",".join(map(str, [position['col'], position['row']]))) if position is not None else ""

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
                ,items.p
                ,items.icon
                ,items.qty
                ,items.stack_size
                ,items.min_qty
                ,items.price_for_min_qty
                ,items.currency
                ,items.identified
                ,items.ilvl
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
                items.item_name = ?
                {pos_condition}
            """,
            [item_name, ]
        )
        return self.cur.fetchone()

    def change_item_qty(self, item_name, position, qty):
        pos_condition = "AND tab_number = {} AND cell_id = {}".format(
            position['tab'], ",".join(map(str, [position['col'], position['row']]))) if position is not None else ""

        self.cur.execute(
            f"""
            UPDATE
                items
            SET
                max_qty = max_qty + ?
            WHERE
                item_name = ?
                {pos_condition}
            """,
            [qty, item_name]
        )

        self.commit()
