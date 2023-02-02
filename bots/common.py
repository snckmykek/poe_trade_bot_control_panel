import time
from dataclasses import dataclass
from operator import itemgetter

import keyboard
import numpy as np
import pyautogui
import pyperclip
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivymd.uix.dialog import MDDialog
from kivymd.uix.textfield import MDTextField
from common import resource_path

Builder.load_file(resource_path('bots\\common.kv'))


class CustomDialog(MDDialog):

    def update_width(self, *args) -> None:
        if self.content_cls.size_hint_x is None:
            self.width = self.content_cls.width + dp(36)
        else:
            super(CustomDialog, self).update_width(*args)

    def on_pre_open(self):
        super(CustomDialog, self).on_open()
        self.update_width()


class CustomMDTextField(MDTextField):
    helper_texts = {
        'int': "Только целые числа",
        'float': "Только числа",
        'str': ""
    }
    text_type = StringProperty("str", options=helper_texts.keys())

    def check_mask_text(self, instance, value):
        self.error = not text_is_correct(self.text_type, value)


def text_is_correct(text_type, value):
    if text_type == 'str' or not value:
        return True
    elif text_type == 'int':
        try:
            int(value)
            return True
        except ValueError:
            return False
    elif text_type == 'float':
        try:
            float(value)
            return True
        except ValueError:
            return False


# region Виртуальный инвентарь

@dataclass
class VirtualInventory:
    """
    """

    rows = 0
    cols = 0
    cells_matrix = np.empty([0, 0])

    def __init__(self, rows, cols):
        self.rows = rows
        self.cols = cols
        self.set_empty_cells_matrix()

    def set_empty_cells_matrix(self):
        self.cells_matrix = np.empty([self.rows, self.cols], dtype=Cell)

        rows, cols = self.cells_matrix.shape

        for row in range(rows):
            for col in range(cols):
                self.cells_matrix[row][col] = Cell(row, col)

    def get_first_cell(self, item='empty') -> tuple:
        sorted_cells = self.get_sorted_cells(item)

        if not sorted_cells:
            raise ValueError(f"Не удалось получить первую ячейку. В инвентаре нет ни одной ячейки с '{item}'")

        return sorted_cells[0]

    def get_last_cell(self, item='empty') -> tuple:
        sorted_cells = self.get_sorted_cells(item)

        if not sorted_cells:
            raise ValueError(f"Не удалось получить последнюю ячейку. В инвентаре нет ни одной ячейки с '{item}'")

        return sorted_cells[-1]

    def get_sorted_cells(self, item, exclude=False):

        cells_with_item = self.get_cells(item, exclude)

        return sorted(cells_with_item, key=itemgetter(1))

    def get_cells(self, item, exclude):

        get_item = np.vectorize(Cell.get_content)

        if exclude:
            cells = list(
                        zip(
                            *np.where(get_item(self.cells_matrix) != item)
                        )
                    )
        else:
            cells = list(
                        zip(
                            *np.where(get_item(self.cells_matrix) == item)
                        )
                    )

        return cells

    def put_item(self, item, qty=1, cell_coord=None):
        if cell_coord:
            row, col = cell_coord
        else:
            row, col = self.get_first_cell()

        cell = self.cells_matrix[row][col]
        cell.put(item, qty)

    def empty_cell(self, row, col):
        cell = self.cells_matrix[row][col]
        cell.empty()

    def get_qty(self, cell_coord):
        row, col = cell_coord
        cell = self.cells_matrix[row][col]
        return cell.get_qty()


@dataclass
class Cell:
    _empty = 'empty'
    _row: int
    _col: int

    content: str = _empty
    qty: int = 0

    def __init__(self, row, col):
        self._row = row
        self._col = col

    def get_content(self):
        return self.content

    def get_qty(self):
        return self.qty

    def put(self, content, qty):
        if self.content != self._empty:
            raise ValueError(f"Не удалось положить предмет '{content}' в виртуальный инвентарь: "
                             f"ячейка ({self._row}, {self._col}) не пуста.")

        self.content = content
        self.qty = qty

    def empty(self):
        if self.content == self._empty:
            raise ValueError(f"Не удалось изъять предмет из виртуального инвентаря: "
                             f"ячейка ({self._row}, {self._col}) пуста.")

        self.content = self._empty
        self.qty = 0


class ItemTransporter:
    pass


def get_item_info(keys: list, cell_coord: list) -> dict:
    pyautogui.moveTo(cell_coord)
    time.sleep(.035)

    item_info = {}

    item_info_text = get_item_info_text_from_clipboard()
    if not item_info_text:
        return item_info

    item_info_parts = [[line for line in part.split('\r\n') if line] for part in item_info_text.split('--------')]

    for key in keys:
        value = find_item_info_by_key(item_info_parts, key)
        item_info.update({key: value})

    return item_info


def get_item_info_text_from_clipboard():
    pyperclip.copy("")
    time.sleep(.015)
    keyboard.send(['ctrl', 46])  # ctrl+c (англ.)
    time.sleep(.035)
    item_info_text = pyperclip.paste()

    return item_info_text


def find_item_info_by_key(item_info_parts, key):

    def get_value_after_startswith(startswith, default_value):
        line = find_line_startswith(item_info_parts, startswith)
        if line:
            return line.split(startswith)[1]
        else:
            return default_value

    if key == 'item_class':
        value = get_value_after_startswith("Item Class: ", "")

    elif key == 'rarity':
        value = get_value_after_startswith("Rarity: ", "")

    elif key == 'quantity':
        str_value = get_value_after_startswith("Stack Size: ", "1/1").split('/')[0]
        value = int(str_value.replace("\xa0", ""))  # мб неразрывный пробел \xa0 (1 234 567)

    elif key == 'ilvl':
        value = get_value_after_startswith("Item Level: ", "")
    elif key == 'item_name':
        rarity = find_item_info_by_key(item_info_parts, 'rarity')

        # Для уников название в 1 части ровно в 3 строке из 4,
        #  а для других - в последней (3 или 4, в зависимости от рарности)
        if rarity == "Unique":
            value = item_info_parts[0][2]
        else:
            value = item_info_parts[0][-1]

    else:
        raise KeyError(f"Для ключа '{key}' не указан алгоритм получения информации по предмету")

    return value


def find_line_startswith(item_info_parts, startswith):
    for item_info_lines in item_info_parts:
        for line in item_info_lines:
            if line.startswith(startswith):
                return line

    return ""

# endregion
