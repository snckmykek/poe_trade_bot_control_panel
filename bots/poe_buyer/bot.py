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

import keyboard as keyboard
import pyautogui
import numpy as np
import requests
import win32gui
from kivy.properties import DictProperty, ListProperty, NumericProperty, BooleanProperty, ObjectProperty, StringProperty
from kivymd.uix.button import MDRectangleFlatIconButton
from kivymd.uix.label import MDLabel
from kivymd.uix.snackbar import MDSnackbar
from win32api import GetSystemMetrics
from kivy.clock import Clock

from bots.bot import Bot, Coord, Simple, Template, get_window_param, to_global
from bots.common import CustomDialog, VirtualInventory, get_item_info
from bots.poe_buyer.db_requests import Database
from bots.poe_buyer.additional_functional import Content, Items, Blacklist

pyautogui.PAUSE = 0


@dataclass
class DealPOETrade(dict):
    id = ""
    chaos_qty = 0
    divine_qty = 0
    item_qty = 0

    account_name = ""
    character_name = ""
    currency = ""
    currency_min_qty = 0
    item = ""
    item_name = ""
    item_min_qty = 0
    c_price = 0
    item_stock = 0
    profit_per_each = 0
    profit = 0
    image = ""
    whisper = ""

    def get(self, attr, default=None):
        return getattr(self, attr, super(DealPOETrade, self).get(attr, default))

    def items(self):
        _items = super(DealPOETrade, self).items()

        return list(_items) + list(self.__dict__.items())

    def get_value(self, key):
        return self.__dict__.get(key, "")


class PoeBuyer(Bot):
    # Обязательные
    icon = 'account-arrow-left'
    name = "ПОЕ: Покупатель"
    key = "poe_buyer"

    # Кастомные
    current_deal: DealPOETrade = DealPOETrade()
    current_deal_dict: dict = DictProperty(dict(DealPOETrade.__dict__))
    db: Database
    chaos_price: float = NumericProperty()
    divine_price: float = NumericProperty()
    deals: list = ListProperty()
    items_left = NumericProperty()
    in_own_hideout = BooleanProperty(False)
    party_accepted: bool = False
    proxies_queue: list = []
    # TODO Сохранять в настройки (или вообще вынести его в настройки, подумать)
    deal_sort_type: Literal['profit_per_each', 'profit'] = StringProperty('profit_per_each')
    start_deal_timestamp: int = 0
    stat: dict = DictProperty({'good': 0, 'skipped': 0, 'bad': 0, 'profit': 0})
    swag: dict = DictProperty({'chaos': 0, 'divine': 0})
    tabs: list
    trade_thread: threading.Thread = None
    party_thread: threading.Thread = None
    virtual_inventory: VirtualInventory = VirtualInventory(5, 12)
    whispers_history: dict = {}
    _last_poe_trade_request: int = 0
    _requests_interval: float = .0

    def __init__(self):
        super(PoeBuyer, self).__init__()

        self.set_task_tab_buttons()
        self.set_tasks()
        self.set_windows()

        self.db = Database(os.path.join(self.app.db_path, f"{self.key}.db"))

        Clock.schedule_once(self.delayed_init)

    # region init
    def set_task_tab_buttons(self):
        self.task_tab_buttons = [
            {
                'text': "Настройки цен",
                'icon': 'alert-box-outline',
                'func': self.open_order
            },
            {
                'text': "Черный список",
                'icon': 'information-outline',
                'func': self.open_blacklist
            },
        ]

    def set_tasks(self):
        self.tasks = [
            {
                'name': "Вход",
                'timer': 60,
                'available_mode': 'after_start',
                'stages': [
                    {
                        'func': self.start_poe,
                        'name': "Запуск ПОЕ по ярлыку"
                    },
                    {
                        'func': self.authorization,
                        'name': "Авторизация"
                    },
                    {
                        'func': self.choice_character,
                        'name': "Выбор перса"
                    },
                    {
                        'func': self.go_home,
                        'name': "ТП в хайдаут"
                    },
                ]
            },
            {
                'name': "Запуск потока ПОЕ трейд и подготовка к торговле",
                'timer': 20,
                'available_mode': 'after_start',
                'stages': [
                    {
                        'func': self.start_poe_trade,
                        'name': "Запросить цены валюты и запустить поток ПОЕ трейд"
                    },
                    {
                        'func': self.go_home_and_update_swag,
                        'name': "Телепорт в ХО и обновление количества валюты"
                    },
                ]
            },
            {
                'name': "Ожидание очереди сделок",
                'timer': 180,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.wait_trade_info,
                        'on_error': {'goto': (2, 0)},
                        'name': "Ждать информацию по валюте и очередь сделок"
                    }
                ]
            },
            {
                'name': "Подготовка",
                'timer': 40,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.prepare_service,
                        'name': "Подготовка служебных данных"
                    },
                ]
            },
            {
                'name': "Запрос сделки",
                'timer': 60,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.set_current_deal,
                        'on_error': {'goto': (2, 0)},
                        'name': "Подобрать и установить текущую сделку"
                    },
                    {
                        'func': self.request_deal,
                        'name': "Отправить виспер"
                    },
                    {
                        'func': self.go_home,
                        'on_error': {'goto': (3, 0)},
                        'name': "ТП в хайдаут"
                    },
                    {
                        'func': self.take_currency,
                        'name': "Взять валюту"
                    },
                    {
                        'func': self.wait_party,
                        'on_error': {'func': lambda x: self.save_current_deal_result(x, 'skipped'), 'goto': (4, 0)},
                        'name': "Ждать пати"
                    },
                    {
                        'func': self.teleport,
                        'on_error': {'goto': (4, 4)},
                        'name': "ТП в хайдаут продавца"
                    },
                ]
            },
            {
                'name': "Сделка",
                'timer': 180,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.wait_trade,
                        'name': "Ждать трейд",
                        'on_error': {'func': lambda x: self.save_current_deal_result(x, 'bad'), 'goto': (3, 0)},
                    },
                    {
                        'func': self.put_currency,
                        'name': "Положить валюту",
                        'on_error': {'goto': (5, 0)}
                    },
                    {
                        'func': self.check_items,
                        'name': "Проверить итемы",
                        'on_error': {'goto': (5, 0)}
                    },
                    {
                        'func': self.set_complete_trade,
                        'name': "Принять сделку"
                    },
                ]
            },
            {
                'name': "Дождаться завершения трейда",
                'timer': 15,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.wait_confirm,
                        'on_error': {'goto': (5, 0)},
                        'name': "Дождаться завершения трейда",
                        'on_complete': {'func': lambda x: self.save_current_deal_result(x, 'completed')}
                    },
                    {
                        'func': self.on_complete_trade,
                        'name': "Действия после трейда"
                    },
                ]
            },
            {
                'name': "Выход из ПОЕ на перерыв",
                'timer': 10,
                'available_mode': 'before_break',
                'stages': [
                    {
                        'func': self.close_poe,
                        'name': "Выход alt+f4"
                    }
                ]
            },
        ]

    def set_variables_setting(self):
        self.variables_setting = {
            'Данные аккаунта': [
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
                Simple(
                    key='bot_name',
                    name="Имя перса, для кика себя из пати",
                    type='str'
                ),
            ],
            'Данные для запросов к АПИ ПОЕ': [
                Simple(
                    key='league',
                    name="Лига",
                    type='str'
                ),
                Simple(
                    key='account_name',
                    name="Имя профиля аккаунта бота (accountName)",
                    type='str'
                ),
                Simple(
                    key='trade_POESESSID',
                    name="Кука POESESSID от любого акка для запросов к АПИ трейда",
                    type='str'
                ),
                Simple(
                    key='proxies_list',
                    name="Список прокси log:pass@ip:port через запятую",
                    type='str'
                ),
                Simple(
                    key='poetrade_info_update_frequency',
                    name="Частота обновления списка сделок (в сек)",
                    type='int'
                ),
            ],
            'Общие настройки': [
                Simple(
                    key='logs_path',
                    name="Путь до логов ПОЕ",
                    type='str'
                ),
                Simple(
                    key='min_chaos',
                    name="Минимальное количество хаосов для работы",
                    type='int'
                ),
                Simple(
                    key='min_divine',
                    name="Минимальное количество дивайнов для работы",
                    type='int'
                ),
                Simple(
                    key='party_timeout',
                    name="Сколько ждать пати после отправки запроса (сек)",
                    type='int'
                ),
                Simple(
                    key='trade_timeout',
                    name="Сколько ждать трейд после телепорта в ХО к продавцу (сек)",
                    type='int'
                ),
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
                Simple(
                    key='additional_mouse_delay',
                    name="Дополнительная задержка после действий мыши (ms)",
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
                Coord(
                    key='coord_currency_tab',
                    name="Координаты валютной вкладки",
                    relative=True,
                    type='coord',
                    window='poe'
                ),
                Coord(
                    key='coord_chaos',
                    name="Координаты ячейки Chaos orb",
                    relative=True,
                    snap_mode='lt',
                    type='coord',
                    window='poe'
                ),
                Coord(
                    key='coord_divine',
                    name="Координаты ячейки Divine orb",
                    relative=True,
                    snap_mode='lt',
                    type='coord',
                    window='poe'
                ),
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
                Template(
                    key='template_accept',
                    name="Кнопка 'ACCEPT' при принятии пати или трейда",
                    region=Coord(
                        key='region_accept',
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
                    key='region_trade_inventory_fields_seller',
                    name="Поле ячеек трейда (продавца)",
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

    def set_windows(self):
        self.windows = {
            'main': {'name': ""},
            'poe': {'name': "Path of Exile", 'expression': ('x', 'y', 'w', 'h')},
            'poe_except_inventory': {'name': "Path of Exile", 'expression': ('x', 'y', 'w - 0.6166 * h', 'h')}

        }

    def delayed_init(self, *_):
        self.task_tab_content = Content()
        self.app.add_task_content()
        self.set_variables_setting()

    # endregion

    def set_deal_sort_type(self, new_type):
        self.deal_sort_type = new_type

    @staticmethod
    def notify_in_developing(*_):
        MDSnackbar(
            MDLabel(text="В разработке")
        ).open()

    def open_order(self, *_):
        content = Items()

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

    def open_blacklist(self, *_):
        content = Blacklist()

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

    def update_current_deal_dict(self):
        # Аттрибуты объекта в виде словаря (кроме функций, методов и __x__), типа .__dict__, но надежнее
        self.current_deal_dict = dict((k, v) for k, v in inspect.getmembers(self.current_deal) if
             not inspect.isfunction(v) and not inspect.ismethod(v) and not inspect.isbuiltin(v) and k[:2] != '__')

    def stub(self, *_):
        print(f"Заглушка: {self.app.current_task}, {self.app.current_stage}")
        time.sleep(1)

    def execute_step(self, task_number, step_number):

        result = {'error': "", 'error_details': "", 'goto': None}

        step = self.get_step(task_number, step_number)

        self.set_empty_log()

        try:
            step['func']()
            if step.get('on_complete') and step['on_complete'].get('func'):
                step['on_complete']['func'](result)

        except Exception as e:
            result['error'] = str(e)
            result['error_detail'] = traceback.format_exc()

            if step.get('on_error') and step['on_error'].get('goto'):
                result['goto'] = step['on_error'].get('goto')

            if step.get('on_error') and step['on_error'].get('func'):
                step['on_error']['func'](result)

        return result

    # region Вход
    def start_poe(self):
        self.click_to('poe_icon', clicks=2)

        # Ждем, пока нормально запустится ПОЕ (при запуске окно перемещается микросекунду)
        window_name = "Path of Exile"
        _window_params = None
        while True:
            if self.stop():
                raise TimeoutError(f"Не запущено окно с именем {window_name}")

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
        self.moveTo(GetSystemMetrics(0) / 2, coord_y)
        self.click(s=.1)
        keyboard.send(['ctrl', 30])  # ctrl+a (англ.)
        keyboard.write(self.v('login'), delay=0)

        coord_y = self.v('coord_password')[1]
        self.moveTo(GetSystemMetrics(0) / 2, coord_y)
        self.click(s=.1)
        keyboard.send(['ctrl', 30])  # ctrl+a (англ.)
        keyboard.write(self.v('password'), delay=0)

        self.click_to('template_login')

    def moveTo(self, x, y, duration=.0):
        pyautogui.moveTo(x, y, duration=duration)
        time.sleep(.015 + self.v('additional_mouse_delay')/1000)

    def click(self, x=None, y=None, s=.0, clicks=1, interval=0.0):
        pyautogui.click(x, y, clicks=clicks, interval=interval)
        time.sleep(.015 + s + self.v('additional_mouse_delay')/1000)

    def choice_character(self):
        self.wait_for_template('template_characters_choosing')

        [keyboard.send('up') for _ in range(30)]
        [keyboard.send('down') for _ in range(self.v('character_number') - 1)]

        self.click_to('coord_play')

    def clear_inventory(self):
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
            self.open_stash()

            self.close_x_tabs()

            # Ждем, пока другой поток примет пати, если его кинули
            if self.find_template(**self.v('template_accept'), move_to_1_1=False):
                time.sleep(1.5)

            self.take_control('clear_inventory')
            self.moveTo(1, 1)
            self.release_control('clear_inventory')
            cells_matrix_from_screen = self.get_cells_matrix_from_screen(region)
            non_empty_cells_coords = sorted(zip(*np.where(cells_matrix_from_screen == 0)), key=itemgetter(1))

            if not len(non_empty_cells_coords):
                break

            if attempts > max_attempts:
                raise TimeoutError(f"Не смог выложить предметы из инвентаря с {attempts} попыток")

            self.check_freeze()

            self.take_control('clear_inventory')

            self.keyDown('ctrl')

            for row, col in non_empty_cells_coords:
                cell_coord = [x_reg + (col + .5) * w_cell, y_reg + (row + .5) * h_cell]
                self.click(cell_coord, clicks=2, interval=.015)
                time.sleep(.015 * attempts)

            self.keyUp('ctrl')

            self.release_control('clear_inventory')

            attempts += 1

        self.virtual_inventory.set_empty_cells_matrix()

    # endregion

    # region Продажа. Запросы на ПОЕ трейд
    def start_poe_trade(self):
        if not self.trade_thread or not self.trade_thread.is_alive():
            self.trade_thread = threading.Thread(target=lambda *_: self.poetrade_loop(), daemon=True)
            self.trade_thread.start()

    def poetrade_loop(self):
        self.update_divine_price()

        while True:
            if self.app.need_break:
                return

            _start = datetime.now()

            try:
                current_order = self.get_current_order()
                self.update_items_left(current_order)
                self.update_offer_list(current_order)
            except Exception as e:
                self.print_log(f"Ошибка в запросе инфы с трейда\n" + str(e))

            _interval = self.v('poetrade_info_update_frequency') - (datetime.now() - _start).total_seconds()
            if _interval > 0:
                time.sleep(_interval)

    def update_divine_price(self):
        # Цена дивайна для конвертации дивайна в хаосы
        divine_deals = self.get_deals(("chaos",), ("divine",))
        prices = [deal.item_min_qty / deal.currency_min_qty for deal in divine_deals]
        avg = sum(prices) / len(prices)

        # Вырезаем прайсфиксерные цены
        _prices = prices.copy()
        for _price in _prices:
            if abs((_price - avg) / avg) > 0.05:  # При отклонении больше чем на 5% от среднего - убираем из списка
                prices.remove(_price)  # Удаляет первый совпавший элемент
                avg = sum(prices) / len(prices)  # Пересчет среднеарифметического

        self.divine_price = round(sum(prices) / len(prices))

        # Цена хаоса для конвертации хаосов в диваны
        chaos_deals = self.get_deals(("divine",), ("chaos",))
        prices = [deal.item_min_qty / deal.currency_min_qty for deal in chaos_deals]
        avg = sum(prices) / len(prices)

        # Вырезаем прайсфиксерные цены
        _prices = prices.copy()
        for _price in _prices:
            if abs((_price - avg) / avg) > 0.05:  # При отклонении больше чем на 5% от среднего - убираем из списка
                prices.remove(_price)  # Удаляет первый совпавший элемент
                avg = sum(prices) / len(prices)  # Пересчет среднеарифметического

        self.chaos_price = sum(prices) / len(prices)

    def get_current_order(self):
        items_i_want = [
            {
                'item': item_settings['item'],
                'name': item_settings['name'],
                'max_price': item_settings['max_price'],
                'bulk_price': item_settings['bulk_price'],
                'image': item_settings['image'],
                'max_qty': item_settings['max_qty']
            } for item_settings in self.db.get_items()
            if (
                    item_settings['use'] and item_settings['max_price']
                    and item_settings['bulk_price'] and item_settings['max_qty']
            )
        ]

        return items_i_want

    def update_items_left(self, current_order):
        items_left = 0
        for item in current_order:
            items_left += item['max_qty']

        self.items_left = items_left

    def update_offer_list(self, items_i_want):

        if len(items_i_want) == 0:
            return

        self.deals = self.get_deals(items_i_want, ("chaos",), deal_sort_type=self.deal_sort_type)

        self.print_log("Сделки обновлены")

    def get_deals(self, items_i_want, items_i_have, min_stock=1, qty_deals=30,
                  deal_sort_type: Literal['profit_per_each', 'profit'] = 'profit_per_each'):
        """
        sort_type. Обычно profit_per_each используется, когда порог закупа (макс прайс) стоит достаточно высокий, и
        хочется пылесосить сначала дешевый товар (хоть и меньше штук за 1 сделку), а потом уже более дорогой. profit
        используется, когда порог закупа (макс прайс) вполне приемлемый и на рынке полно этого товара, и лучше закупить
        пачку подороже, чем одну штуку дешево, тогда профит за "прыжок" будет больше, а балком всё равно быстро уйдет
        :return: Отсортированный по профиту список сделок
        """

        def deal_completed(_deal_id):
            return _deal_id in last_deals_100

        def in_blacklist(_character_name):
            return _character_name in blacklist

        self.update_proxies_queue()

        last_deals_100 = self.db.get_last_deals(100)
        blacklist = self.db.get_blacklist()
        deals = []

        league = self.v('league')

        headers = {
            "Host": "www.pathofexile.com",
            "Connection": "keep - alive",
            "Content-Length": "127",
            "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
            "Accept": "*/*",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua-mobile": "?0",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/99.0.4844.82 Safari/537.36",
            "sec-ch-ua-platform": '"Windows"',
            "Origin": "https://www.pathofexile.com",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": f"https://www.pathofexile.com/trade/exchange/{league}",
            "Accept-Encoding": "gzip,deflate,br",
            "Accept-Language": "q=0.9,en-US;q=0.8,en;q=0.7",
            "Cookie": f"POESESSID={self.v('trade_POESESSID')}"
        }

        # Ссылка для запроса к странице с балком
        url = fr"https://www.pathofexile.com/api/trade/exchange/{league}"

        _last_poe_trade_request = time.time()
        for item_i_want in items_i_want:
            simple_item = isinstance(item_i_want, str)
            for item_i_have in items_i_have:

                # Запрос поиска
                data = {
                    "query": {
                        "status": {
                            "option": "online"
                        },
                        "want": [item_i_want if simple_item else item_i_want['item'], ],
                        "have": [item_i_have, ],
                        "minimum": min_stock

                    },
                    "sort": {
                        "have": "asc"
                    },
                    "engine": "new"
                }

                # Перерыв зависит от ответа АПИ ПОЕ
                current_proxy_info = self.proxies_queue.pop(0)
                _delta = math.ceil(self._requests_interval - (time.time() - current_proxy_info['last_use']))
                if current_proxy_info['last_use'] and _delta > 0:
                    self.print_log(f"Прокси: {current_proxy_info['proxy']}, ожидание: {_delta}")
                    time.sleep(_delta)

                proxy = current_proxy_info['proxy']
                if proxy:
                    proxies = {'https': f'http://{proxy}'}
                else:
                    proxies = {}

                # Получаем результат поиска по запросу
                # Если не работает, значит не установлен pip install brotli
                response_request = requests.post(url, headers=headers, json=data, proxies=proxies)

                current_proxy_info['last_use'] = int(time.time())
                self.proxies_queue.append(current_proxy_info)

                response = response_request.json()

                interval_rule = response_request.headers['X-Rate-Limit-Ip'].split(",")[-1].split(":")
                self._requests_interval = float(interval_rule[1]) / float(interval_rule[0]) + .5

                try:
                    # Код ошибки "Лимит запросов за промежуток времени (меняется динамически)"
                    if response['error']['code'] == 3:
                        while response['error']['code'] == 3:
                            retry_after = float(response_request.headers[
                                          'Retry-After'])  # Время "блокировки" при нарушении частоты
                            self.print_log(f"Из-за лимита запроса время ожидания до некст трейда: {retry_after}")
                            time.sleep(retry_after)

                            response_request = requests.post(url, headers=headers, json=data)
                            response = response_request.json()
                except Exception:
                    pass

                results = response["result"]

                for deal_id, deal_info in results.items():
                    account_info = deal_info['listing']['account']
                    offer_info = deal_info['listing']['offers'][0]

                    # Если сделка уже была (просто не прогрузился поетрейд) или чел в БЛ, то она не нужна
                    if deal_completed(deal_id) or in_blacklist(account_info['lastCharacterName']) \
                            or self.skip_by_whispers_history(account_info['lastCharacterName']):
                        continue

                    deal = DealPOETrade()
                    deal.id = deal_id
                    deal.account_name = account_info['name']
                    deal.character_name = account_info['lastCharacterName']
                    deal.currency = offer_info['exchange']['currency']
                    deal.currency_min_qty = offer_info['exchange']['amount']
                    deal.exchange_whisper = offer_info['exchange']['whisper']
                    deal.item = offer_info['item']['currency']
                    deal.item_min_qty = offer_info['item']['amount']
                    deal.item_stock = math.floor(
                        offer_info['item']['stock'] / offer_info['item']['amount']) * offer_info['item']['amount']
                    deal.item_whisper = offer_info['item']['whisper']
                    deal.whisper = deal_info['listing']['whisper']

                    deal.c_price = deal.currency_min_qty / deal.item_min_qty * (
                        self.chaos_price if deal.currency == 'divine' else 1)
                    if not simple_item:
                        deal.profit_per_each = math.floor(
                            (item_i_want['bulk_price'] - deal.c_price)
                        )
                        deal.profit = deal.profit_per_each * deal.item_stock
                        deal.image = item_i_want['image']
                        deal.item_name = item_i_want['name']

                    if simple_item or deal.c_price <= item_i_want['max_price']:
                        deals.append(deal)

        if deal_sort_type == 'profit_per_each':
            # Сортировка по профиту за штуку + количеству всего
            deals = sorted(deals,
                           key=lambda d: (
                               d.profit_per_each if d.profit_per_each else (d.item_min_qty / d.currency_min_qty),
                               d.item_stock
                           ),
                           reverse=True
                           )
        elif deal_sort_type == 'profit':
            # Сортировка по профиту общему профиту от сделки
            deals = sorted(deals,
                           key=lambda d: d.profit if d.profit else (d.item_min_qty / d.currency_min_qty),
                           reverse=True
                           )

        return deals[:qty_deals]

    def update_proxies_queue(self):
        proxies_list = self.v('proxies_list').split(",")

        if not proxies_list:
            if not self.proxies_queue or self.proxies_queue[0]['proxy'] is not None:
                self.proxies_queue = [{'proxy': None, 'last_use': 0}, ]
            return

        for proxy in proxies_list:
            if proxy not in [element['proxy'] for element in self.proxies_queue]:
                self.proxies_queue.append({'proxy': proxy, 'last_use': 0})

        for i in range(len(proxies_list)):
            element = self.proxies_queue[-(i + 1)]
            if element['proxy'] not in proxies_list:
                self.proxies_queue.remove(element)

    def skip_by_whispers_history(self, character_name):
        last_whisper = self.whispers_history.get(character_name)

        if last_whisper:
            delta = int(datetime.now().timestamp()) - last_whisper
            if delta < 120:
                return True

        return False

    def go_home_and_update_swag(self):
        self.go_home(forced=True)

        self.update_swag()

    def update_swag(self):

        chaos_qty = 0
        divine_qty = 0
        while not chaos_qty or not divine_qty:
            self.try_to_open_currency_tab()

            chaos_info = get_item_info(['item_name', 'quantity'], self.v('coord_chaos'))
            if 'chaos' in chaos_info.get('item_name', "").lower():
                chaos_qty = chaos_info.get('quantity', 0)

            divine_info = get_item_info(['item_name', 'quantity'], self.v('coord_divine'))
            if 'divine' in divine_info.get('item_name', "").lower():
                divine_qty = divine_info.get('quantity', 0)

        self.swag.update({'chaos': chaos_qty, 'divine': divine_qty})

    # endregion

    # region Продажа. Ожидание очереди сделок

    def wait_trade_info(self):
        if not self.deals and not self.in_own_hideout:
            self.go_home()

        while self.swag['chaos'] == 0 and self.swag['divine'] == 0:
            if self.stop():
                raise TimeoutError("Не дождался инфы о валюте в стеше")

        while self.chaos_price == 0 or self.divine_price == 0:
            if self.stop():
                raise TimeoutError("Не дождался инфы о цене дивайна")

        while not self.deals:
            if self.stop():
                raise TimeoutError("Не дождался инфы о сделках")

    # endregion

    # region Продажа. Подготовка

    def prepare_service(self):
        min_chaos = self.v('min_chaos')
        min_divine = self.v('min_divine')
        if self.swag['chaos'] < min_chaos or self.swag['divine'] < min_divine:
            self.go_home(forced=True)
            raise ValueError(f"Количество валюты меньше минимальных значений. Chaos: {self.swag['chaos']} "
                             f"(минимум: {min_chaos}), Divine: {self.swag['divine']} (минимум: {min_divine})")

        self.start_deal_timestamp = int(datetime.now().timestamp())
        self.reset_control_queue()

        if not self.party_thread or not self.party_thread.is_alive():
            self.party_thread = threading.Thread(target=lambda *_: self.accept_party(), daemon=True)
            self.party_thread.start()

    # endregion

    # region Продажа. Запрос сделки
    def set_current_deal(self):
        if not self.deals:  # Если нет некст сделки, очищаем поля текущей, чтоб не висело
            self.current_deal = DealPOETrade()

        current_deal = self.deals.pop(0)

        while self.skip_by_whispers_history(current_deal.character_name):
            current_deal = self.deals.pop(0)

        available_c = self.swag['chaos'] + self.swag['divine'] * self.chaos_price

        items_settings = self.db.get_items(current_deal.item)
        qty_left = items_settings[0]['max_qty'] if items_settings else 0

        if qty_left == 0:
            self.remove_deals_with_item(current_deal.item)
            raise ValueError(f"Товар {current_deal.item} полностью закуплен")

        item_amount = 0
        currency_amount = 0
        while item_amount + current_deal.item_min_qty <= qty_left \
                and item_amount + current_deal.item_min_qty <= current_deal.item_stock \
                and currency_amount + current_deal.currency_min_qty <= available_c:
            item_amount += current_deal.item_min_qty
            currency_amount += current_deal.currency_min_qty

        if item_amount == 0:
            raise ValueError(f"Количество для покупки: 0. ID сделки: {current_deal.id}")

        current_deal.divine_qty = currency_amount // self.divine_price
        current_deal.chaos_qty = currency_amount % self.divine_price

        if self.swag['chaos'] < current_deal.chaos_qty or self.swag['divine'] < current_deal.divine_qty:
            raise ValueError(f"Недостаточно валюты. Нужно/всего: "
                             f"Дивайны {current_deal.divine_qty}/{self.swag['divine']}, "
                             f"Хаосы {current_deal.chaos_qty}/{self.swag['chaos']}")

        current_deal.item_qty = item_amount
        current_deal.profit = current_deal.profit_per_each * item_amount

        if current_deal.divine_qty == 0:
            exchange_whispers_part = current_deal.exchange_whisper.format(current_deal.chaos_qty)
        elif current_deal.chaos_qty == 0:
            exchange_whispers_part = "{0} Divine Orb".format(current_deal.divine_qty)
        else:
            exchange_whispers_part = "{0} Divine Orb and {1} Chaos Orb".format(
                current_deal.divine_qty, current_deal.chaos_qty)

        current_deal.whisper = current_deal.whisper.format(
            current_deal.item_whisper.format(current_deal.item_qty), exchange_whispers_part
        )

        self.current_deal = current_deal
        self.update_current_deal_dict()

    def remove_deals_with_item(self, item):
        for i in reversed(range(len(self.deals))):
            if self.deals[i].item == item:
                self.deals.pop(i)

    def deal_amount_text(self):
        text = ""
        if self.current_deal.divine_qty:
            text += f"{self.current_deal.divine_qty} d"
        if self.current_deal.chaos_qty:
            if text:
                text += ", "
            text += f"{self.current_deal.chaos_qty} c"

        if not text:
            text = "0"

        return text

    def request_deal(self):
        self.clear_logs()
        self.send_to_chat(self.current_deal.whisper)
        self.whispers_history.update({self.current_deal.character_name: int(datetime.now().timestamp())})

        self.party_accepted = False

    def take_currency(self):
        if self.stop():
            raise TimeoutError("Не смог взять валюту из стеша")

        self.open_stash()

        # Пока выкладываем каждый раз тупа всё из инвентаря и скрином проверяем, что всё ок
        self.clear_inventory()

        self.update_swag()
        self.from_stash_to_inventory(self.current_deal.divine_qty, 'divine')
        self.from_stash_to_inventory(self.current_deal.chaos_qty, 'chaos')

    def open_stash(self):
        # Кликаем на надпись "STASH" пока не увидим признак открытого стеша или не закончится время
        template_stash_header_settings = self.v('template_stash_header')

        attempt = 0
        while True:

            if attempt > 3:
                self.go_home(forced=True)

            if self.find_template(**template_stash_header_settings):
                return

            self.click_to('template_stash')

            if self.stop():
                raise TimeoutError("Не смог открыть стеш")
            else:
                time.sleep(.5)

    # Временно использую clear_inventory
    def from_inventory_to_stash(self):

        region = self.v('region_inventory_fields')

        cells_for_empty = self.virtual_inventory.get_sorted_cells('empty', exclude=True)

        max_attempts = self.v('max_attempts')
        attempts = 0
        while cells_for_empty:
            self.items_from_cells(region, cells_for_empty)

            if attempts > 0:
                self.close_x_tabs()

            cells_from_screen = self.get_cells_matrix_from_screen(region)
            cells_for_empty_from_screen = list(zip(*np.where(cells_from_screen == 0)))

            cells_for_empty = list(set(cells_for_empty) & set(cells_for_empty_from_screen))

            attempts += 1

            if attempts > max_attempts:
                raise TimeoutError(f"Не удалось выложить валюту из инвентаря с {attempts} попыток")

    def from_inventory_to_trade(self):
        inv_region = self.v('region_inventory_fields')
        trade_my_region = self.v('region_trade_inventory_fields_my')
        trade_template_settings = self.v('template_trade')

        cells_for_empty = self.virtual_inventory.get_sorted_cells('empty', exclude=True)

        while True:
            if not self.find_template(**trade_template_settings):
                raise TimeoutError("Трейд закрылся до завершения")

            self.items_from_cells(inv_region, cells_for_empty)
            time.sleep(.75)

            trade_cells_matrix = self.get_cells_matrix_from_screen(trade_my_region)
            trade_non_empty_cells = list(zip(*np.where(trade_cells_matrix == 0)))
            if len(cells_for_empty) == len(trade_non_empty_cells):
                return

            if self.stop():
                raise TimeoutError("Не смог выложить валюту из инвентаря в трейд")

    def items_from_cells(self, region, cells):

        for row, col in cells:
            self.check_freeze()

            self.take_control('items_from_cells')
            self.keyDown('ctrl')
            self.moveTo(int(region[0] + region[2] * (col + 0.5) / 12),
                        int(region[1] + region[3] * (row + 0.5) / 5),
                        .05)
            self.click()
            self.keyUp('ctrl')
            self.release_control('items_from_cells')

    def try_to_open_currency_tab(self):
        self.open_stash()
        self.move_mouse_and_click(self.v('coord_currency_tab'))
        time.sleep(1)

    def get_cells_matrix_from_screen(self, region, item=None):
        """
        Возвращает 2-мерную матрицу, где 0 - пустая ячейка, 1 - заполненная найденным шаблоном (даже пустым)
        :param item:
        :param region:
        :return:
        """

        if item:
            item_size = [int(region[-2] / 12), int(region[-1] / 5)]
            coords = self.find_template(
                region, f"https://web.poecdn.com{self.db.get_poe_item_image(item)}",
                item_size, mode='all', use_mask=True, is_item=True
            )
        else:
            template_settings = self.v('template_empty_field')
            coords = self.find_template(region, template_settings['path'], template_settings['size'], mode='all')

        if not coords:
            coords = []

        cell_size = [int(region[3] / 5), int(region[2] / 12)]
        inventory_cells = np.zeros([5, 12])
        for x, y, w, h in coords:
            index_y = math.floor((y + cell_size[0] / 2) / cell_size[0])
            index_x = math.floor((x + cell_size[1] / 2) / cell_size[1])
            inventory_cells[index_y][index_x] = 1

        return inventory_cells

    def close_x_tabs(self):
        variable_value = self.v('template_x_button')

        xywh = self.find_template(**variable_value, mode='all')

        while xywh:
            for _xywh in xywh:
                self.check_freeze()

                x, y, w, h = _xywh
                self.move_mouse_and_click(to_global(variable_value['region'], [x + w * .5, y + h * .5]))

            time.sleep(1)

            xywh = self.find_template(**variable_value, mode='all')

    def from_stash_to_inventory(self, amount, currency):

        if not amount:
            return

        if currency == 'divine':
            currency_coord = self.v('coord_divine')
            stack = self.swag['divine']
        elif currency == 'chaos':
            currency_coord = self.v('coord_chaos')
            stack = self.swag['chaos']
        else:
            raise ValueError(f"Неверно указана валюта: '{currency}'")

        item_name_from_clipboard = get_item_info(['item_name', ], currency_coord).get('item_name', "")
        while currency not in item_name_from_clipboard.lower():
            self.try_to_open_currency_tab()
            item_name_from_clipboard = get_item_info(['item_name', ], currency_coord).get('item_name', "")

            if self.stop():
                raise TimeoutError("Не смог открыть валютную вкладку")

        if stack < amount:
            raise ValueError(f"Недостаточно валюты '{currency}': всего {stack}, требуется {amount}")

        stack_size = 10
        inv_region = self.v('region_inventory_fields')

        whole_part = math.floor(amount // stack_size)
        remainder_part = amount % stack_size

        self.put_whole_part_in_inventory(inv_region, currency_coord, currency, stack_size, whole_part)
        self.put_remainder(inv_region, currency_coord, currency, remainder_part)

    # Пока не используется, тупа clear_inventory
    def empty_cell_with_remainder(self, inv_region, item, stack_size):
        last_cell_coord = self.virtual_inventory.get_last_cell(item)
        last_cell_qty = self.virtual_inventory.get_qty(last_cell_coord)

        if last_cell_qty == stack_size:  # Полная ячейка
            return

        self.take_control('empty_cell_with_remainder')
        self.moveTo(int(inv_region[0] + inv_region[2] * (last_cell_coord[1] + 0.5) / 12),
                    int(inv_region[1] + inv_region[3] * (last_cell_coord[0] + 0.5) / 5),
                    .2)
        self.keyDown('ctrl')
        self.click()
        self.keyUp('ctrl')
        self.release_control('empty_cell_with_remainder')

        self.virtual_inventory.empty_cell(*last_cell_coord)

    def put_remainder(self, inv_region, currency_coord, item, qty):
        if qty == 0:
            return

        first_empty_cell = self.virtual_inventory.get_first_cell()
        cell_coords = [int(inv_region[0] + inv_region[2] * (first_empty_cell[1] + 0.5) / 12),
                       int(inv_region[1] + inv_region[3] * (first_empty_cell[0] + 0.5) / 5)]

        attempt = 0
        counted = 0
        while qty != counted:

            if self.stop() or attempt >= 5:
                raise TimeoutError("Не смог выложить нецелую часть валюты")

            self.check_freeze()

            self.take_control('put_remainder')

            if attempt:
                time.sleep(.2)
                self.keyDown('ctrl')
                time.sleep(.1)
                self.click(*cell_coords, clicks=2, interval=.015)
                time.sleep(.1)
                self.keyUp('ctrl')
                time.sleep(.15)

            self.moveTo(*currency_coord, .1)
            time.sleep(.15)
            self.keyDown('Shift')
            time.sleep(.15)
            self.click()
            time.sleep(.15)
            self.keyUp('Shift')
            time.sleep(.15)
            pyautogui.write(f'{qty}')
            time.sleep(.15)
            pyautogui.press('Enter')
            time.sleep(.15)
            self.moveTo(*cell_coords)
            time.sleep(.15)
            self.click()
            time.sleep(.15)

            self.release_control('put_remainder')

            counted = self.get_items_qty_in_cell(cell_coords)

            attempt += 1

        self.virtual_inventory.put_item(item, qty, first_empty_cell)

        self.moveTo(1, 1)

    @staticmethod
    def keyDown(key):
        pyautogui.keyDown(key)
        time.sleep(.025)

    @staticmethod
    def keyUp(key):
        pyautogui.keyUp(key)
        time.sleep(.025)

    def change_whole_part_in_inventory(self, inv_region, currency_coord, item, stack_size, whole_part_qty):
        cells_with_item = self.virtual_inventory.get_sorted_cells(item)
        current_whole_part_qty = len(cells_with_item)

        delta = whole_part_qty - current_whole_part_qty

        while delta != 0:
            if delta > 0:  # Нужно доложить в инвентарь из стеша
                for cell_coord in self.virtual_inventory.get_sorted_cells('empty'):
                    self.take_control('change_whole_part_in_inventory')
                    self.moveTo(*currency_coord, .2)
                    self.keyDown('ctrl')
                    self.click()
                    self.keyUp('ctrl')
                    self.take_control('change_whole_part_in_inventory')

                    self.virtual_inventory.put_item(item, stack_size, cell_coord)

                    delta = len(set([]) & set([]))

                    if delta == 0:
                        break

            elif delta < 0:  # Нужно убрать из инвентаря
                cells_for_empty = list(reversed(cells_with_item))[-1 * delta]
                self.items_from_cells(inv_region, cells_for_empty)

            if self.stop():
                raise TimeoutError("Не смог выложить валюту из стеша")

    # Временно вместо недописанной change_whole_part_in_inventory
    def put_whole_part_in_inventory(self, inv_region, currency_coord, item, stack_size, whole_part_qty):

        if whole_part_qty == 0:
            return

        cells_with_items_from_screen = []

        attempt = 0
        counted = 0
        while counted != whole_part_qty:
            if self.stop() or attempt >= 5:
                raise TimeoutError(f"Не смог взять валюту из стеша с {attempt} попыток")

            self.check_freeze()

            self.take_control('change_whole_part_in_inventory')

            self.moveTo(*currency_coord)

            self.keyDown('ctrl')
            need_more = whole_part_qty - counted
            for i in range(need_more):  # Нужно доложить в инвентарь из стеша
                time.sleep(.015)
                self.click(*currency_coord, s=.035)

            self.keyUp('ctrl')

            self.release_control('change_whole_part_in_inventory')

            self.close_x_tabs()

            cells_matrix_from_screen = self.get_cells_matrix_from_screen(inv_region, item)
            cells_with_items_from_screen = list(zip(*np.where(cells_matrix_from_screen == 1)))
            counted = len(cells_with_items_from_screen)

            attempt += 1

        # Записываем в вирт инвент
        for cell_pos in cells_with_items_from_screen:
            self.virtual_inventory.put_item(item, stack_size, cell_pos)

        self.take_control('change_whole_part_in_inventory')
        self.moveTo(1, 1)
        self.release_control('change_whole_part_in_inventory')

    def get_cells_with_item_amount(self, region, item=None):
        cells_matrix = self.get_cells_matrix_from_screen(region, item)
        cells = list(zip(*np.where(cells_matrix == 1)))
        counted = len(cells)
        return counted

    def count_sellers_items(self, inv_region, item_name):
        cells_matrix = self.get_cells_matrix_from_screen(inv_region)
        cells_positions = list(zip(*np.where(cells_matrix == 0)))  # Непустые

        qty = 0
        for row, col in cells_positions:
            cell_coords = self.cell_coords_by_position(inv_region, col, row)
            qty += self.get_items_qty_in_cell(cell_coords, item_name)

        # TODO Вынести в отдельную логику ситуации, когда товар большой на несколько яч ячейках (сейчас каждую считает)
        if item_name == 'Prime Chaotic Resonator':
            qty = round(qty/4)

        self.print_log(f"Подсчитано {item_name}: {qty}")

        return qty

    def get_items_qty_in_cell(self, cell_coords, item_name=""):
        self.take_control('get_items_qty_in_cell')
        item_info = get_item_info(['quantity', 'item_name'], cell_coords)
        self.release_control('get_items_qty_in_cell')

        qty = 0
        item_name_from_clipboard = item_info.get('item_name', "")
        if not item_name or item_name.lower() in item_name_from_clipboard.lower():
            qty = item_info.get('quantity', 0)

        return qty

    @staticmethod
    def cell_coords_by_position(inv_region, col, row):
        return [int(inv_region[0] + inv_region[2] * (col + 0.5) / 12),
                int(inv_region[1] + inv_region[3] * (row + 0.5) / 5)]

    def wait_party(self):
        timeout = self.v('party_timeout')
        _start = datetime.now()

        while not self.party_accepted:
            if self.check_chat_need_skip():
                raise TimeoutError("Пропускаем по стоп-слову из чата")

            if self.stop() or (timeout and (datetime.now() - _start).total_seconds() > timeout):
                raise TimeoutError("Не дождался пати")
            else:
                time.sleep(.5)

    def accept_party(self):

        template_settings = self.v('template_accept')

        while True:
            if not self.party_accepted:
                self.check_freeze()

                xywh = self.find_template(**template_settings, move_to_1_1=False)

                if xywh:
                    self.take_control('accept_party')
                    x, y, w, h = xywh
                    self.moveTo(*to_global(template_settings['region'], [x + w * .5, y + h * .5]))
                    self.click()
                    self.release_control('accept_party')

                    self.party_accepted = True

            time.sleep(.5)

    def teleport(self):
        self.send_to_chat(f"/hideout {self.current_deal.character_name}")
        time.sleep(self.v('waiting_for_teleport'))
        self.wait_for_template('template_game_loaded')  # Ждем загрузку

        # Если мы не можем сделать ТП, то мы в пати с кем-то другим. Проверяем этот вариант
        if self.check_cannot_teleport():
            self.leave_party()
            self.clear_logs()
            self.party_accepted = False
            raise TimeoutError(f"Не смог сделать ТП, игрок {self.current_deal.character_name} не в пати")

        self.in_own_hideout = False

    def check_cannot_teleport(self):
        with open(self.v('logs_path'), 'r', encoding="utf-8") as f:
            for line in f:
                if 'You cannot currently access' in line:
                    return True

        return False

    # endregion

    # region Продажа. Сделка
    def wait_trade(self):
        trade_template_settings = self.v('template_trade')
        timeout = self.v('trade_timeout')

        _start = datetime.now()

        while True:
            time.sleep(.5)

            if self.find_template(**trade_template_settings):
                break

            self.click_to('template_accept', wait_template=False)

            if self.stop() or (timeout and (datetime.now() - _start).total_seconds() > timeout):
                self.leave_party()
                raise TimeoutError("Не дождался трейда")

        self.clear_logs()

    def put_currency(self):
        self.from_inventory_to_trade()

    def check_items(self):
        qty = 0
        region = self.v('region_trade_inventory_fields_seller')
        trade_template_settings = self.v('template_trade')
        while qty < self.current_deal.item_qty:

            if not self.find_template(**trade_template_settings):
                raise TimeoutError("Трейд закрылся до завершения")

            qty = self.count_sellers_items(region, self.current_deal.item_name)

            if self.stop():
                raise TimeoutError(
                    f"Неверное количество предметов для сделки {qty} (нужно {self.current_deal.item_qty})")

    def set_complete_trade(self):
        try:
            if self.wait_for_template('template_cancel_complete_trade', .1, accuracy=.8):
                # Уже нажата кнопка (т.к. вместо нее появилась кнопка отмены трейда)
                return
        except TimeoutError:
            pass

        self.click_to('template_complete_trade', accuracy=.8)

    # endregion

    # region После трейда

    def wait_confirm(self):
        while True:
            trade_status = self.get_trade_status()

            if trade_status == 'accepted':
                return
            elif trade_status == 'cancelled':
                raise ValueError("Трейд отменен продавцом")

            if self.stop():
                raise TimeoutError("Не дождался подтверждения от продавца")

            time.sleep(.5)

    def on_complete_trade(self):
        self.say_ty()
        self.leave_party()
        self.reduce_orders_quantity()
        self.reduce_swag()

    def leave_party(self):
        self.send_to_chat(f"/kick {self.v('bot_name')}")

    def reduce_orders_quantity(self):
        self.db.change_item_qty(self.current_deal.item, -self.current_deal.item_qty)

    def reduce_swag(self):
        self.swag['divine'] -= self.current_deal.divine_qty
        self.swag['chaos'] -= self.current_deal.chaos_qty

    def get_trade_status(self):
        with open(self.v('logs_path'), 'r', encoding="utf-8") as f:
            for line in f:
                if 'Trade accepted.' in line:
                    return 'accepted'
                elif 'Trade cancelled.' in line:
                    return 'cancelled'

    def check_chat_need_skip(self):
        skip_words = ['not online', 'afk', 'gone', 'sold', 'dnd']

        with open(self.v('logs_path'), 'r', encoding="utf-8") as f:
            for line in f:
                for word in skip_words:
                    if word in line.lower():
                        print(f"Пропускаем по стоп слову '{word}' в строке '{line}'")
                        return True

        return False

    def say_ty(self):
        self.send_to_chat(f"@{self.current_deal.character_name} ty")

    # endregion

    # region Выход из ПОЕ на перерыв
    def close_poe(self):
        window_name = "Path of Exile"
        while True:
            if self.stop():
                raise TimeoutError(f"Не смог закрыть окно {window_name}")

            time.sleep(3)

            hwnd = win32gui.FindWindow(None, window_name)
            if hwnd:
                win32gui.SetForegroundWindow(hwnd)  # Выводим на передний план окно

                keyboard.send("alt+f4")  # Закрываем его
            else:
                return

    # endregion

    # region Общие функции

    def clear_logs(self):
        open(self.v('logs_path'), 'w').close()  # Очистка логов перед трейдом

    def go_home(self, forced=False):
        if self.in_own_hideout and not forced:
            return

        template_stash_settings = self.v('template_stash')
        while True:
            self.wait_for_template('template_game_loaded')
            self.send_to_chat("/hideout")
            time.sleep(self.v('waiting_for_teleport'))

            if self.find_template(**template_stash_settings):
                self.in_own_hideout = True
                break

    @staticmethod
    def send_to_chat(message):
        pyautogui.press('enter')
        time.sleep(.15)
        keyboard.write(message, delay=0)
        time.sleep(.05)
        pyautogui.press('enter')

    def save_current_deal_result(self, result, state):
        self.db.save_deal_history([
            self.start_deal_timestamp,  # date
            self.current_deal.id,  # id
            self.current_deal.character_name,
            bool(state == 'completed'),  # completed
            result['error'],  # error
            self.current_deal.item,
            self.current_deal.item_qty,
            self.current_deal.c_price,
            self.current_deal.profit,  # profit
            int(datetime.now().timestamp()) - self.start_deal_timestamp  # deal_time
        ])

        if state == 'completed':
            self.stat['good'] += 1
            self.stat['profit'] += self.current_deal.profit
            self.db.update_blacklist((self.start_deal_timestamp, self.current_deal.character_name, 1, 0))
        else:
            if state == 'skipped':  # Не кинул пати продавец
                self.stat['skipped'] += 1
                self.db.update_blacklist((self.start_deal_timestamp, self.current_deal.character_name, 0, 1))
            else:  # Ошибка во время трейда
                self.stat['bad'] += 1

    # endregion
