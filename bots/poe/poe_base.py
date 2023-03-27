import inspect
import math
import os
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from operator import itemgetter
from typing import Literal

import cv2
import keyboard as keyboard
import pyautogui
import numpy as np
import pyperclip
import requests
import win32gui
from kivy.lang import Builder
from kivy.properties import DictProperty, ListProperty, NumericProperty, BooleanProperty, StringProperty, ObjectProperty
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRectangleFlatIconButton
from kivymd.uix.label import MDLabel
from matplotlib import pyplot as plt
from win32api import GetSystemMetrics
from kivy.clock import Clock

from bots.bot import Bot, Coord, Simple, Template, get_window_param, to_global
from bots.common import CustomDialog
from bots.poe.buyer.db_requests import Database
from bots.poe.buyer.additional_functional import Content, Items, Blacklist
from common import resource_path, abs_path_near_exe
from controllers import mouse_controller, hotkey_controller
from errors import StopStepError

Builder.load_file(os.path.abspath(os.path.join(os.path.dirname(__file__), "poe_base.kv")))


class PoeBase(Bot):
    # Обязательные
    icon = 'account-arrow-left'
    name = "ПОЕ: База"
    key = "poe_base"

    # Кастомные
    virtual_inventory = None
    poe_helper = None

    def __init__(self):
        super(PoeBase, self).__init__()
        self.virtual_inventory = VirtualInventory(5, 12)

        self.poe_helper = Helper()

        self.variables_setting = {
            'Данные для входа': [
                Simple(
                    key='login',
                    name="Логин бота",
                    type='str'
                ),
                Simple(
                    key='password',
                    name="Пароль бота",
                    type='str'
                ),
                Simple(
                    key='character_number',
                    name="Порядковый номер перса (отсчет сверху)",
                    type='int'
                ),
            ],
            'Общие настройки': [
                Simple(
                    key='button_delay_ms',
                    name="Дополнительная задержка после действий мыши и клавиатуры (ms)",
                    type='int'
                ),
            ],
            'Инвентарь': [
                Simple(
                    key='waiting_for_teleport',
                    name="Сколько примерно длится загрузка при телепорте (сек)",
                    type='int'
                ),
                Simple(
                    key='max_attempts',
                    name="Максимальное число попыток, чтобы взять/выложить валюту",
                    type='int'
                ),
            ],
            'Окно: раб. стол': [
                Template(
                    key='poe_icon',
                    name="Иконка ПОЕ на раб столе ГЛАВНОГО экрана",
                    region=Coord(
                        key='region_poe_icon',
                        name="",
                        relative=True,
                        snap_mode='lt',
                        type='region',
                        window='main'
                    ),
                    relative=True,
                    type='template',
                    window='main'
                )
            ],
            'Окно: Path of Exile (вход)': [
                Coord(
                    key='coord_mail',
                    name="Координаты поля, куда вводить логин/почту",
                    relative=True,
                    type='coord',
                    window='poe'
                ),
                Coord(
                    key='coord_password',
                    name="Координаты поля, куда вводить пароль",
                    relative=True,
                    type='coord',
                    window='poe'
                ),
                Template(
                    key='template_login',
                    name="Кнопка 'LOG IN'",
                    region=Coord(
                        key='region_login',
                        name="",
                        relative=True,
                        snap_mode='lt',
                        type='region',
                        window='poe'
                    ),
                    relative=True,
                    type='template',
                    window='poe'
                ),
                Template(
                    key='template_characters_choosing',
                    name="Шаблон, определяющий страницу выбора перса",
                    region=Coord(
                        key='region_characters_choosing',
                        name="",
                        relative=True,
                        snap_mode='rt',
                        type='region',
                        window='poe'
                    ),
                    relative=True,
                    type='template',
                    window='poe'
                ),
                Coord(
                    key='coord_play',
                    name="Координаты кнопки 'PLAY'",
                    relative=True,
                    snap_mode='rt',
                    type='coord',
                    window='poe'
                ),
            ],
            'Окно: Path of Exile (игра)': [
                Template(
                    key='template_game_loaded',
                    name=
                    "Статичный кусок экрана, однозначно говорящий о загрузке локи (например, сиськи телки где мана)",
                    region=Coord(
                        key='region_game_loaded',
                        name="",
                        relative=True,
                        snap_mode='rb',
                        type='region',
                        window='poe'
                    ),
                    relative=True,
                    type='template',
                    window='poe'
                ),
                Template(
                    key='template_stash_header',
                    name="'Сундук' в шапке стеша (или другая часть, желательно без букв)",
                    region=Coord(
                        key='region_stash_header',
                        name="",
                        relative=True,
                        snap_mode='lt',
                        type='region',
                        window='poe'
                    ),
                    relative=True,
                    type='template',
                    window='poe'
                ),
                Template(
                    key='template_stash',
                    name="Надпись 'STASH' над закрытым стешем",
                    region=Coord(
                        key='region_stash',
                        name="",
                        relative=True,
                        snap_mode='lt',
                        type='region',
                        window='poe'
                    ),
                    relative=True,
                    type='template',
                    window='poe'
                ),
                Coord(
                    key='region_inventory_fields',
                    name="Поле ячеек инвентаря (как можно точнее по краю внешних ячеек)",
                    relative=True,
                    snap_mode='rt',
                    type='region',
                    window='poe'
                ),
                Coord(
                    key='region_trade_inventory_fields_my',
                    name="Поле ячеек трейда (мои)",
                    relative=True,
                    snap_mode='ct',
                    type='region',
                    window='poe_except_inventory'
                ),
                Coord(
                    key='region_trade_inventory_fields_his',
                    name="Поле ячеек трейда (того, с кем трейд)",
                    relative=True,
                    snap_mode='ct',
                    type='region',
                    window='poe_except_inventory'
                ),
                Template(
                    key='template_trade',
                    name="Полусфера в шапке трейда (или другой элемент для определения, что трейд открыт)",
                    region=Coord(
                        key='region_trade',
                        name="",
                        relative=True,
                        snap_mode='ct',
                        type='region',
                        window='poe_except_inventory'
                    ),
                    relative=True,
                    type='template',
                    window='poe_except_inventory'
                ),
                Template(
                    key='template_complete_trade',
                    name="Шаблон кнопки для завершения трейда",
                    region=Coord(
                        key='region_complete_trade',
                        name="",
                        relative=True,
                        snap_mode='ct',
                        type='region',
                        window='poe_except_inventory'
                    ),
                    relative=True,
                    type='template',
                    window='poe_except_inventory'
                ),
                Template(
                    key='template_cancel_complete_trade',
                    name="Шаблон кнопки для отмены завершения трейда",
                    region=Coord(
                        key='region_cancel_complete_trade',
                        name="",
                        relative=True,
                        snap_mode='ct',
                        type='region',
                        window='poe_except_inventory'
                    ),
                    relative=True,
                    type='template',
                    window='poe_except_inventory'
                ),
                Template(
                    key='template_x_button',
                    name="Кнопка 'X' на сообщениях в инвентаре (когда пати приняли и тд)",
                    region=Coord(
                        key='region_x_button',
                        name="",
                        relative=True,
                        snap_mode='rt',
                        type='region',
                        window='poe'
                    ),
                    relative=True,
                    type='templates',
                    window='poe'
                ),
                Template(
                    key='template_empty_field',
                    name="Пустая ячейка инвентаря",
                    region=Coord(
                        key='region_empty_field',
                        name="",
                        relative=True,
                        snap_mode='lt',
                        type='region',
                        window='poe'
                    ),
                    relative=True,
                    type='template',
                    window='poe'
                ),
            ]
        }

        self.task_tab_buttons.extend(
            [
                {
                    'text': "POE: Helper",
                    'icon': 'alert-box-outline',
                    'func': self.open_poe_helper
                },
            ]
        )

    def open_poe_helper(self, *_):
        content = self.poe_helper

        dialog = CustomDialog(
            auto_dismiss=False,
            title=content.title,
            type="custom",
            content_cls=content,
            buttons=[
                MDRectangleFlatIconButton(
                    icon=dialog_button['icon'],
                    text=dialog_button['text'],
                    theme_text_color="Custom",
                    text_color=self.app.theme_cls.primary_color,
                    on_release=dialog_button['on_release']
                ) for dialog_button in content.buttons
            ],
        )

        dialog.content_cls.dialog_parent = dialog
        dialog.bind(on_pre_open=content.on_pre_open)
        dialog.open()

    def stub(self, *_):
        print(f"Заглушка: {self.app.current_task}, {self.app.current_stage}")
        time.sleep(1)

    # region Вход
    def start_poe(self):
        self.click_to('poe_icon', clicks=2)

        # Ждем, пока нормально запустится ПОЕ (при запуске окно перемещается микросекунду)
        window_name = "Path of Exile"
        _window_params = None
        while True:
            if self.stop():
                raise StopStepError(f"Не запущено окно с именем {window_name}")

            time.sleep(2)

            try:
                window_params = get_window_param('poe', 'xywh_hwnd')
            except Exception as e:
                continue

            # Только когда в одном и том же месте окно находится - всё ок
            if _window_params and window_params and _window_params == window_params:
                # Выводим на передний план окно
                win32gui.SetForegroundWindow(window_params[-1])
                return
            else:
                _window_params = window_params

    def authorization(self):
        self.wait_for_template('template_login')

        coord_y = self.v('coord_mail')[1]
        self.mouse_move_and_click(GetSystemMetrics(0) / 2, coord_y, sleep_after=.1)
        keyboard.press_and_release(['ctrl', 30])  # ctrl+a (англ.)
        keyboard.write(self.v('login'), delay=0)

        coord_y = self.v('coord_password')[1]
        self.mouse_move_and_click(GetSystemMetrics(0) / 2, coord_y, sleep_after=.1)
        keyboard.press_and_release(['ctrl', 30])  # ctrl+a (англ.)
        keyboard.write(self.v('password'), delay=0)

        self.click_to('template_login')

    def choice_character(self):
        self.wait_for_template('template_characters_choosing')

        [keyboard.press_and_release('up') for _ in range(30)]
        [keyboard.press_and_release('down') for _ in range(self.v('character_number') - 1)]

        self.click_to('coord_play')

    # endregion

    # region Работа с инвентарем

    def clear_inventory(self, manual=False):
        region = self.v('region_inventory_fields')

        rows = 12
        cols = 5

        x_reg = region[0]
        y_reg = region[1]
        w_cell = region[2] / rows
        h_cell = region[3] / cols

        max_attempts = self.v('max_attempts')
        attempts = 0
        while True:
            self.check_freeze()

            if not manual:
                self.open_stash()

            non_empty_cells = self.get_non_empty_cells(region)

            if not len(non_empty_cells):
                break

            if attempts > max_attempts:
                raise StopStepError(f"Не смог выложить предметы из инвентаря с {attempts} попыток")

            with mouse_controller:
                self.key_down('ctrl')
                for row, col in non_empty_cells:
                    cell_coord = [x_reg + (col + .5) * w_cell, y_reg + (row + .5) * h_cell]
                    if manual:
                        # pyautogui.moveTo(*cell_coord)
                        pyautogui.click(*cell_coord, clicks=2)
                        time.sleep(.013)
                    else:
                        self.mouse_click(cell_coord, clicks=2, interval=.015)
                    time.sleep(.015 * attempts)
                self.key_up('ctrl')

            if manual:
                break

            attempts += 1

        self.virtual_inventory.set_empty_cells_matrix()

    def open_stash(self, move_to_1_1=True):

        attempt = 0
        while True:
            if self.find_template('template_stash_header', move_to_1_1=move_to_1_1):
                return

            self.click_to('template_stash')

            if self.stop() or attempt > 3:
                raise StopStepError("Не смог открыть стеш")
            else:
                time.sleep(.5)

    def items_from_cells(self, region, cells):

        for row, col in cells:
            self.check_freeze()

            with mouse_controller:
                self.key_down('ctrl')
                self.mouse_move(int(region[0] + region[2] * (col + 0.5) / 12),
                                int(region[1] + region[3] * (row + 0.5) / 5),
                                .05)
                self.mouse_click()
                self.key_up('ctrl')

    def get_non_empty_cells(self, region, need_clear_region=True):
        cells_matrix_from_screen = self.get_cells_matrix_from_screen(region, need_clear_region=need_clear_region)
        non_empty_cells_coords = sorted(zip(*np.where(cells_matrix_from_screen == 0)), key=itemgetter(1))
        return non_empty_cells_coords

    def get_empty_cells(self, region, need_clear_region=True):
        cells_matrix_from_screen = self.get_cells_matrix_from_screen(region, need_clear_region=need_clear_region)
        empty_cells_coords = sorted(zip(*np.where(cells_matrix_from_screen == 1)), key=itemgetter(1))
        return empty_cells_coords

    def get_cells_with_item(self, region, item, need_clear_region=True):
        cells_matrix_from_screen = self.get_cells_matrix_from_screen(region, item=item,
                                                                     need_clear_region=need_clear_region)
        cells_with_item = list(zip(*np.where(cells_matrix_from_screen == 1)))
        return cells_with_item

    def get_cells_matrix_from_screen(self, region, item=None, need_clear_region=True):
        """
        Возвращает 2-мерную матрицу, где 0 - ячейка без найденного шаблона,
         1 - заполненная найденным шаблоном (даже шаблоном пустой ячейки)
        """

        if item:
            template_path = f"https://web.poecdn.com{self.get_item_image(item)}"
            item_size = self.get_item_size(item)
            template_size = [int(region[-2] / 12) * item_size['w'], int(region[-1] / 5) * item_size['h']]
        else:
            template_settings = self.v('template_empty_field')
            template_path = template_settings['path']
            template_size = template_settings['size']

        template = {
            'path': template_path,
            'size': template_size
        }

        template.update(
            self.get_template_params(template_path, template_size, use_mask=bool(item), is_item=bool(item))
        )

        if need_clear_region:
            img = self.get_screen_region_after_clear(region)
        else:
            img = self.get_screen_region(region, True)

        coords = self.match_templates(img, template, 'all')

        if not coords:
            coords = []

        cell_size = [int(region[3] / 5), int(region[2] / 12)]
        inventory_cells = np.zeros([5, 12])
        for x, y, w, h in coords:
            index_y = math.floor((y + cell_size[0] / 2) / cell_size[0])
            index_x = math.floor((x + cell_size[1] / 2) / cell_size[1])
            inventory_cells[index_y][index_x] = 1

        return inventory_cells

    def get_screen_region_after_clear(self, region):
        x_tab_template = self.v('template_x_button')

        poe_xywh = get_window_param('poe')
        extend_w_value = (poe_xywh[0] + poe_xywh[2]) - (region[0] + region[2])
        x_tab_h = x_tab_template['size'][1] * 2
        extended_inventory_region = [
            region[0],
            region[1] - x_tab_h,
            region[2] + extend_w_value,
            region[3] + x_tab_h
        ]

        w = extended_inventory_region[2]
        h = extended_inventory_region[3]

        while True:
            img = self.get_screen_region(extended_inventory_region, True)
            x_tab_offset_x = w - x_tab_h

            x_tabs_img = img[:, x_tab_offset_x:w]
            x_tabs_coords = self.match_templates(x_tabs_img, x_tab_template, 'all')

            accept_coords = self.match_templates(img, 'template_accept', 'once')

            if not x_tabs_coords and not accept_coords:
                break

            for x_tab_coords in x_tabs_coords:
                self.check_freeze()

                x_tab_x, x_tab_y, x_tab_w, x_tab_h = x_tab_coords
                self.mouse_move_and_click(
                    *to_global(
                        extended_inventory_region, [x_tab_offset_x + x_tab_x + x_tab_w * .5, x_tab_y + x_tab_h * .5]
                    )
                )

            time.sleep(1)

        return img[x_tab_h:h, 0:w - extend_w_value]

    def get_item_image(self, item):
        raise NotImplementedError("Не переназначена функция, для каждого бота нужно назначить свою")

    def get_item_size(self, item):
        raise NotImplementedError("Не переназначена функция, для каждого бота нужно назначить свою")

    def get_template_params(self, template_path, template_size, accuracy=None, use_mask=False, is_item=False):
        """
        :return: template_gray, mask, normalized_accuracy
        """
        template = self.get_template(template_path, template_size)
        mask = self.get_template_mask(template, use_mask, is_item)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        normalized_accuracy = self.get_normalized_accuracy(accuracy, template_gray)

        return {'template_gray': template_gray, 'mask': mask, 'normalized_accuracy': normalized_accuracy}

    @staticmethod
    def get_template(path, size):
        if path.startswith("http"):  # Это url
            template_b = requests.get(path).content
            template = np.asarray(bytearray(template_b), dtype="uint8")
            template = cv2.imdecode(template, cv2.IMREAD_UNCHANGED)
        else:
            template = (plt.imread(abs_path_near_exe(f"images/templates/{path}")) * 255).astype(np.uint8)

        template = cv2.resize(template, size)

        return template

    @staticmethod
    def get_template_mask(template, use_mask, is_item=False):
        if use_mask:
            template_size = template.shape[:2]
            mask = np.zeros(template_size).astype('uint8')
            for y in range(template_size[0]):
                for x in range(template_size[1]):
                    if is_item and y < template_size[0] * .4 and x < template_size[1] * .5:
                        # Добавляем в маску область, где указано количество, чтобы не учитывать при поиске по шаблону
                        mask[y][x] = 0
                    else:
                        mask[y][x] = template[y][x][3]
        else:
            mask = None

        return mask

    def from_stash_to_inventory(self, amount, item, stack_size, stack, item_size=(1, 1)):
        if not amount:
            return

        inv_region = self.v('region_inventory_fields')

        if stack < amount:
            raise StopStepError(f"Недостаточно '{item}': всего {stack}, требуется {amount}")

        whole_part = math.floor(amount // stack_size)
        remainder_part = amount % stack_size

        self.put_whole_part_in_inventory(inv_region, item, stack_size, whole_part, item_size)
        self.put_remainder(inv_region, item, remainder_part, item_size)
        
    def from_inventory_to_trade(self):
        inv_region = self.v('region_inventory_fields')
        trade_my_region = self.v('region_trade_inventory_fields_my')

        cells_for_empty = self.virtual_inventory.get_sorted_cells('empty', exclude=True)

        while True:
            if not self.find_template('template_trade'):
                raise StopStepError("Трейд закрылся до завершения")

            self.items_from_cells(inv_region, cells_for_empty)
            time.sleep(1)

            trade_non_empty_cells = self.get_non_empty_cells(trade_my_region, need_clear_region=False)
            if len(cells_for_empty) == len(trade_non_empty_cells):
                return

            if self.stop():
                raise StopStepError("Не смог выложить из инвентаря в трейд")

    def put_remainder(self, inv_region, item, qty, item_size):
        if qty == 0:
            return

        item_coord, item_qty_left_in_cell = self.get_item_coord_and_qty(item)

        first_empty_cell = self.virtual_inventory.get_first_cell()
        cell_coords = [int(inv_region[0] + inv_region[2] * (first_empty_cell[1] + 0.5) / 12),
                       int(inv_region[1] + inv_region[3] * (first_empty_cell[0] + 0.5) / 5)]

        attempt = 0
        counted = 0
        while qty != counted:

            if self.stop() or attempt >= 5:
                raise StopStepError(f"Не смог выложить нецелую часть валюты c {attempt} попыток")

            self.check_freeze()

            with mouse_controller:

                if attempt:
                    time.sleep(.2)
                    self.key_down('ctrl', sleep_after=.1)
                    self.mouse_click(*cell_coords, clicks=2, interval=.015, sleep_after=.1)
                    self.key_up('ctrl', sleep_after=.15)

                if qty > item_qty_left_in_cell:
                    raise StopStepError(f"Недостаточно {item} в ячейке")

                elif qty == item_qty_left_in_cell:
                    self.mouse_move(*item_coord, duration=.1, sleep_after=.15)
                    self.key_down('Ctrl', sleep_after=.15)
                    self.mouse_click(sleep_after=.15)
                    self.key_up('Ctrl', sleep_after=.15)

                else:
                    self.mouse_move(*item_coord, duration=.1, sleep_after=.15)
                    self.key_down('Shift', sleep_after=.15)
                    self.mouse_click(sleep_after=.15)
                    self.key_up('Shift', sleep_after=.15)
                    pyautogui.write(f'{qty}')
                    time.sleep(.15)
                    pyautogui.press('Enter')
                    time.sleep(.15)
                    self.mouse_move(*cell_coords, sleep_after=.15)
                    self.mouse_click(sleep_after=.15)

            counted = self.get_items_qty_in_cell(cell_coords)

            attempt += 1

        self.virtual_inventory.put_item(item, qty, first_empty_cell, item_size)

        with mouse_controller:
            self.mouse_move(1, 1)

    def get_item_coord_and_qty(self, item):
        raise NotImplementedError("Для каждого бота ПОЕ функция должна быть реализована отдельно")

    def put_whole_part_in_inventory(self, inv_region, item, stack_size, whole_part_qty, item_size):
        if whole_part_qty == 0:
            return

        item_coord, item_qty_left_in_cell = self.get_item_coord_and_qty(item)

        if item_qty_left_in_cell < whole_part_qty * stack_size:
            raise StopStepError(f"Недостаточно {item} в ячейке")

        cells_with_items_from_screen = []

        attempt = 0
        counted = 0
        while counted != whole_part_qty:
            if self.stop() or attempt >= 5:
                raise StopStepError(f"Не смог взять целую часть итемов из стеша с {attempt} попыток")

            self.check_freeze()

            need_more = whole_part_qty - counted

            with mouse_controller:
                self.mouse_move(*item_coord)

                self.key_down('ctrl', sleep_after=.15)
                self.mouse_click(*item_coord, clicks=need_more, interval=.035, sleep_after=.035)
                self.key_up('ctrl', sleep_after=.15)

            cells_with_items_from_screen = self.get_cells_with_item(inv_region, item=item, need_clear_region=True)
            counted = len(cells_with_items_from_screen)

            attempt += 1

        # Записываем в вирт инвент
        for cell_pos in cells_with_items_from_screen:
            self.virtual_inventory.put_item(item, stack_size, cell_pos, item_size)

        with mouse_controller:
            self.mouse_move(1, 1)

    def count_items(self, inv_region, item_name):
        cells_positions = self.get_non_empty_cells(inv_region, need_clear_region=False)

        qty = 0
        for row, col in cells_positions:
            cell_coords = self.cell_coords_by_position(inv_region, col, row)
            qty += self.get_items_qty_in_cell(cell_coords, item_name)

        # TODO Вынести в отдельную логику ситуации, когда товар большой на несколько яч ячейках (сейчас каждую считает)
        if item_name == 'Prime Chaotic Resonator':
            qty = round(qty / 4)

        self.print_log(f"Подсчитано {item_name}: {qty}")

        return qty

    @staticmethod
    def get_items_qty_in_cell(cell_coords, item_name=""):
        with mouse_controller:
            item_info = get_item_info(['quantity', 'item_name'], cell_coords)

        qty = 0
        item_name_from_clipboard = item_info.get('item_name', "")
        if not item_name or item_name.lower() in item_name_from_clipboard.lower():
            qty = item_info.get('quantity', 0)

        return qty

    @staticmethod
    def cell_coords_by_position(inv_region, col, row):
        return [int(inv_region[0] + inv_region[2] * (col + 0.5) / 12),
                int(inv_region[1] + inv_region[3] * (row + 0.5) / 5)]

    # endregion

    # region Прочее

    def close_poe(self):
        window_name = "Path of Exile"
        while True:
            if self.stop():
                raise StopStepError(f"Не смог закрыть окно {window_name}")

            time.sleep(3)

            hwnd = win32gui.FindWindow(None, window_name)
            if hwnd:
                win32gui.SetForegroundWindow(hwnd)  # Выводим на передний план окно

                keyboard.send("alt+f4")  # Закрываем его
            else:
                return

    def clear_logs(self):
        open(self.v('logs_path'), 'w').close()

    @staticmethod
    def send_to_chat(message):
        pyautogui.press('enter')
        time.sleep(.15)
        keyboard.write(message, delay=0)
        time.sleep(.05)
        pyautogui.press('enter')

    # endregion


class Helper(MDBoxLayout):
    title = "Настройки POE: Helper"
    dialog_parent = ObjectProperty()
    buttons = []

    def __init__(self, **kwargs):
        super(Helper, self).__init__(**kwargs)

        self.buttons = [
            {
                'text': "Отменить",
                'icon': 'window-close',
                'on_release': self.cancel
            },
            {
                'text': "Сохранить",
                'icon': 'check',
                'on_release': self.save
            },
        ]

        self.add_hotkeys()

    def set_hotkeys(self):
        pass

    def on_pre_open(self, *args):
        pass

    def cancel(self, *args):
        self.dialog_parent.dismiss()

    def save(self, *args):
        # TODO save_hotkeys
        self.add_hotkeys()

        self.dialog_parent.dismiss()

    def add_hotkeys(self):
        def clear_inv(*_):
            try:
                MDApp.get_running_app().bot.clear_inventory(manual=True)
            except Exception as e:
                MDApp.get_running_app().set_status(f"{str(type(e))} {str(e)}")

        hotkey_controller.add_hotkey('f10', clear_inv)


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

    def put_item(self, item, qty=1, cell_coord=None, item_size=(1, 1)):
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
