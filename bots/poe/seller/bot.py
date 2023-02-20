import json
import math
import os
import random
import threading
import time
from datetime import datetime
from operator import itemgetter

import keyboard as keyboard
import pyautogui
import numpy as np
import requests
import win32gui
from kivy.properties import DictProperty, ListProperty, NumericProperty
from kivymd.uix.button import MDRectangleFlatIconButton
from kivymd.uix.snackbar import Snackbar
from win32api import GetSystemMetrics
from kivy.clock import Clock

from bots.bot import Bot, Coord, Simple, Template, get_window_param
from bots.common import CustomDialog, image_to_int
from bots.poe.buyer import Database
from bots.poe.buyer import Content, Items


class PoeSeller(Bot):
    # Обязательные
    icon = 'account-arrow-left'
    name = "ПОЕ: Продавец"
    key = "poe_seller"

    # Кастомные
    current_deal: dict = DictProperty({
        'id': "",
        'character_name': "",
        'available_item_stock': 0,
        'exchange_currency': "chaos",
        'exchange_amount': 0,
        'item_currency': "",
        'item_amount': 0,
        'profit': 0,
        'image': "",
    })
    db: Database
    divine_price: int = NumericProperty()
    deals: list = ListProperty()
    deal_history: dict = {}
    stat: dict = DictProperty({'good': 0, 'skipped': 0, 'bad': 0, 'profit': 0})
    swag: dict = DictProperty({'chaos': 0, 'divine': 0})
    tabs: list
    trade_thread: threading.Thread = None

    def __init__(self):
        super(PoeSeller, self).__init__()

        self.task_tab_buttons = [
            {
                'text': "Настройки цен",
                'icon': 'alert-box-outline',
                'func': self.open_order
            },
            {
                'text': "Черный список",
                'icon': 'information-outline',
                'func': self.notify_in_developing
            },
        ]

        self.tasks = [
            {
                'name': "Вход",
                'timer': 30,
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
                ]
            },
            {
                'name': "Запуск потока ПОЕ трейд",
                'timer': 20,
                'available_mode': 'after_start',
                'stages': [
                    {
                        'func': self.start_poe_trade,
                        'name': "Запросить количество валюты и запустить поток ПОЕ трейд"
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
                    {
                        'func': self.go_home,
                        'on_error': {'goto': (3, 0)},
                        'name': "ТП в хайдаут"
                    },
                    {
                        'func': self.check_open_stash,
                        'on_error': {'goto': (3, 0)},
                        'name': "Проверить, открывается ли стеш"
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
                        'on_error': {'goto': (4, 0)},
                        'name': "Отправить запрос и ждать пати"
                    },
                    {
                        'func': self.take_currency,
                        'on_error': {'goto': (4, 2)},
                        'name': "Взять валюту"
                    },
                    {
                        'func': self.teleport,
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
                        'on_error': {'goto': (3, 0)}
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
                        'name': "Дождаться завершения трейда"
                    },
                    {
                        'func': self.say_ty,
                        'name': "Благодарение"
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
        self.variables_setting = {
            'Тестовые сделки': [
                Simple(
                    key='test_deals',
                    name="Сделки для теста (json-строка)",
                    type='str'
                ),
            ],
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
                    key='account_POESESSID',
                    name="Кука POESESSID от текущего бота",
                    type='str'
                ),
                Simple(
                    key='trade_POESESSID',
                    name="Кука POESESSID от любого акка для запросов к АПИ трейда",
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
                    name="Сколько ждать пати после отправки запроса",
                    type='int'
                ),
                Simple(
                    key='trade_timeout',
                    name="Сколько ждать трейд после телепорта в ХО к продавцу",
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
                    key='coord_tabs',
                    name="Список координат всех вкладок в стеше по порядку (слева-направо/сверху-вниз)",
                    relative=True,
                    type='coord_list',
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

        self.windows = {
            'main': {'name': ""},
            'poe': {'name': "Path of Exile", 'expression': ('x', 'y', 'w', 'h')},
            'poe_except_inventory': {'name': "Path of Exile", 'expression': ('x', 'y', 'w - 0.6166 * h', 'h')}

        }

        self.db = Database(os.path.join(self.app.db_path, f"{self.key}.db"))

        Clock.schedule_once(self.delayed_init)

    def delayed_init(self, *_):
        self.task_tab_content = Content()
        self.app.add_task_content()

    @staticmethod
    def notify_in_developing(*_):
        Snackbar(text="В разработке").open()

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

    def stub(self, *_):
        print(f"Заглушка: {self.app.current_task}, {self.app.current_stage}")
        time.sleep(1)

    # region Вход
    def start_poe(self):
        self.click_to('poe_icon', clicks=2)

        # Ждем, пока нормально запустится ПОЕ (при запуске окно перемещается микросекунду)
        window_name = "Path of Exile"
        window_xywh = None
        while True:
            if self.stop():
                return f"Не запущено окно с именем {window_name}"

            time.sleep(2)

            _window_xywh = get_window_param('poe')
            # Только когда в одном и том же месте окно находится - всё ок
            if _window_xywh and window_xywh and window_xywh == _window_xywh:
                # Выводим на передний план окно (но расположение слетает в 0,0)
                hwnd = win32gui.FindWindow(None, window_name)
                win32gui.SetForegroundWindow(hwnd)
                return
            else:
                window_xywh = _window_xywh

    def authorization(self):
        self.wait_for_template('template_login')

        coord_y = self.v('coord_mail')[1]
        pyautogui.moveTo([GetSystemMetrics(0) / 2, coord_y])
        pyautogui.click()
        time.sleep(.1)
        keyboard.send('ctrl+a')
        keyboard.write(self.v('login'), delay=0)

        coord_y = self.v('coord_password')[1]
        pyautogui.moveTo([GetSystemMetrics(0) / 2, coord_y])
        pyautogui.click()
        time.sleep(.1)
        keyboard.send('ctrl+a')
        keyboard.write(self.v('password'), delay=0)

        self.click_to('template_login')

    def choice_character(self):
        self.wait_for_template('template_characters_choosing')

        [keyboard.send('up') for _ in range(30)]
        [keyboard.send('down') for _ in range(self.v('character_number') - 1)]

        self.click_to('coord_play')

    # endregion

    # region Продажа. Запросы на ПОЕ трейд
    def start_poe_trade(self):
        if not self.trade_thread or not self.trade_thread.is_alive():
            self.trade_thread = threading.Thread(target=lambda *_: self.poetrade_loop(), daemon=True)
            self.trade_thread.start()

    def poetrade_loop(self):
        self.update_tabs_and_swag()
        self.update_divine_price()

        while True:
            if self.app.need_break:
                return

            _start = datetime.now()

            self.update_offer_list()

            if self.app.s(self.key, 'debug'):  # !
                return

            _interval = self.v('poetrade_info_update_frequency') - (datetime.now() - _start).total_seconds()
            if _interval > 0:
                time.sleep(_interval)

    def update_tabs_and_swag(self):
        headers = {
            "Host": "www.pathofexile.com",
            "Connection": "keep - alive",
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
            "Accept-Encoding": "gzip,deflate,br",
            "Accept-Language": "q=0.9,en-US;q=0.8,en;q=0.7",
            "Cookie": f"POESESSID={self.v('account_POESESSID')}"
        }

        url = fr"https://www.pathofexile.com/character-window/get-stash-items?league={self.v('league')}" \
              fr"&accountName={self.v('account_name')}&tabs=1&tabIndex=0"

        response_request = requests.post(url, headers=headers)
        response = response_request.json()

        # TODO: if len(response['tabs']) != self.v('coord_tabs'): ERROR!
        self.tabs = [{
            'n': tab['n'],
            'i': tab['i'],
            'type': tab['type'],
            'coord': coord
        } for tab, coord in zip(response['tabs'], self.v('coord_tabs'))]

        # В первом запросе получили инфу по 0 вкладке. Если вдруг валютная вкладка не 0, тогда перезапрашиваем
        currency_tab_index = next((tab['i'] for tab in self.tabs if tab['type'] == 'CurrencyStash'), 0)

        if currency_tab_index != 0:
            url = fr"https://www.pathofexile.com/character-window/get-stash-items?league={self.v('league')}" \
                  fr"&accountName={self.v('account_name')}&tabs=1&tabIndex={currency_tab_index}"

            response_request = requests.post(url, headers=headers)
            response = response_request.json()

        self.swag = {
            'chaos': next((item['stackSize'] for item in response['items'] if item['x'] == 2), 0),  # x=2 ячейка хаосов
            'divine': next((item['stackSize'] for item in response['items'] if item['x'] == 20), 0)
            # x=20 ячейка дивайнов
        }

    def update_divine_price(self):
        prices = [deal['item_amount'] / deal['exchange_amount'] for deal in self.get_deals(("chaos",), ("divine",))]
        avg = sum(prices) / len(prices)

        # Вырезаем прайсфиксерные цены
        _prices = prices.copy()
        for _price in _prices:
            if abs((_price - avg) / avg) > 0.05:  # При отклонении больше чем на 5% от среднего - убираем из списка
                prices.remove(_price)  # Удаляет первый совпавший элемент
                avg = sum(prices) / len(prices)  # Пересчет среднеарифметического

        self.divine_price = round(sum(prices) / len(prices))

    def update_offer_list(self):

        if self.app.s(self.key, 'test'):
            self.deals = json.loads(self.v('test_deals').replace('I\'d', 'Id').replace('\'', '\"'))
            return

        items_i_want = [
            {
                'item': item_settings['item'],
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

        self.deals = self.get_deals(items_i_want, ("chaos",))

    # endregion

    # region Общие функции
    @staticmethod
    def send_to_chat(message):
        pyautogui.press('enter')
        time.sleep(.02)
        keyboard.write(message, delay=0)
        time.sleep(.02)
        pyautogui.press('enter')

    def get_deals(self, items_i_want, items_i_have, min_stock=1, qty_deals=20):
        """
        :param qty_deals:
        :param items_i_want: Список Словарей
        :param items_i_have: Список строк
        :param min_stock:
        :return: Отсортированный по профиту список сделок
        """

        league = self.v('league')

        deals = []

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

        requests_interval = 0
        for item_i_want in items_i_want:
            simple_item = isinstance(item_i_want, str)
            for item_i_have in items_i_have:
                # Перерыв зависит от ответа АПИ ПОЕ
                time.sleep(requests_interval)

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

                # Получаем результат поиска по запросу
                # Если не работает, значит не установлен pip install brotli
                response_request = requests.post(url, headers=headers, json=data)
                response = response_request.json()

                interval_rule = response_request.headers['X-Rate-Limit-Ip'].split(",")[-1].split(":")
                requests_interval = float(interval_rule[1]) / float(interval_rule[0]) + .5

                try:
                    # Код ошибки "Лимит запросов за промежуток времени (меняется динамически)"
                    if response['error']['code'] == 3:
                        while response['error']['code'] == 3:
                            time.sleep(
                                float(response_request.headers[
                                          'Retry-After']))  # Время "блокировки" при нарушении частоты
                            response_request = requests.post(url, headers=headers, json=data)
                            response = response_request.json()
                except Exception:
                    pass

                results = response["result"]

                for deal_id, deal_info in results.items():
                    deal = {
                        'id': deal_id,
                        'account_name': deal_info['listing']['account']['name'],
                        'character_name': deal_info['listing']['account']['lastCharacterName'],
                        'exchange_currency': deal_info['listing']['offers'][0]['exchange']['currency'],
                        'exchange_amount': deal_info['listing']['offers'][0]['exchange']['amount'],
                        'exchange_whisper': deal_info['listing']['offers'][0]['exchange']['whisper'],
                        'item_currency': deal_info['listing']['offers'][0]['item']['currency'],
                        'item_amount': deal_info['listing']['offers'][0]['item']['amount'],
                        'item_stock': deal_info['listing']['offers'][0]['item']['stock'],
                        'item_whisper': deal_info['listing']['offers'][0]['item']['whisper'],
                        'whisper': deal_info['listing']['whisper']
                    }

                    # Если сделка уже была (просто не прогрузился поетрейд) или чел в БЛ, то она не нужна
                    if self.deal_completed(deal['id']) or self.db.checkin_blacklist(deal['character_name']):
                        continue

                    deal.update({'c_price': deal['exchange_amount'] / deal['item_amount'] * (
                        self.divine_price if deal['exchange_currency'] == 'divine' else 1)})
                    deal.update({'available_item_stock':
                                     math.floor(deal['item_stock'] / deal['item_amount']) * deal['item_amount']})
                    if not simple_item:
                        deal.update({'profit': math.floor(
                            (item_i_want['bulk_price'] - deal['c_price']) * deal['available_item_stock'])})
                        deal.update({'image': item_i_want['image']})

                    if simple_item or deal['c_price'] <= item_i_want['max_price']:
                        deals.append(deal)

        deals = sorted(deals,
                       key=lambda d: d['profit'] if d.get('profit') is not None
                       else deal['exchange_amount'] / deal['item_amount'],
                       reverse=True)

        return deals[:qty_deals]

    def ty(self, username):
        self.send_to_chat(f'@{username} ty')

    # endregion

    # region Продажа. Подготовка
    def prepare_service(self):
        min_chaos = self.v('min_chaos')
        min_divine = self.v('min_divine')
        if self.swag['chaos'] < min_chaos or self.swag['divine'] < min_divine:
            raise ValueError(f"Количество валюты меньше минимальных значений. Chaos: {self.swag['chaos']} "
                             f"(минимум: {min_chaos}), Divine: {self.swag['divine']} (минимум: {min_divine})")

        if len(list(self.deal_history.keys())) == 11:  # FIXME: исправить, падает с ошибкой когда только 1 ключ {error: ""}
            self.db.save_deal_history(list(self.deal_history.values()))

            if self.deal_history['completed']:
                self.stat['good'] += 1
                self.stat['profit'] += self.deal_history['profit']
                self.db.update_blacklist((self.deal_history['date'], self.deal_history['character_name'], 1, 0))
            else:
                if self.deal_history['last_stage'] == "3,0":  # Не кинул пати продавец
                    self.stat['skipped'] += 1
                    self.db.update_blacklist((self.deal_history['date'], self.deal_history['character_name'], 0, 1))
                else:
                    self.stat['bad'] += 1

        self.deal_history = {
            'date': int(datetime.now().timestamp()),
            'id': "",
            'character_name': "",
            'completed': False,
            'error': "",
            'last_stage': "0,0",
            'item': "",
            'qty': 0,
            'c_price': 0,
            'profit': 0,
            'deal_time': 0
        }

    def go_home(self):
        self.wait_for_template('template_game_loaded')  # Ждем загрузку

        self.send_to_chat("/hideout")
        time.sleep(3)

        self.wait_for_template('template_game_loaded')  # Ждем загрузку

    def check_open_stash(self):
        self.open_stash()  # Открываем стеш
        self.open_currency_tab()  # Нажимаем на валютную вкладку

    def open_currency_tab(self):
        # TODO нужны проверки, если нет вкладки или еще какие-то траблы, проверка - нажата ли реально вкладка и тд
        coord = next((tab['coord'] for tab in self.tabs if tab['type'] == 'CurrencyStash'), 0)
        pyautogui.moveTo(coord)
        time.sleep(.1)
        pyautogui.click()

    def open_stash(self):
        # Кликаем на надпись "STASH" пока не увидим признак открытого стеша или не закончится время
        template_stash_header_settings = self.v('template_stash_header')

        while True:

            if self.find_template(**template_stash_header_settings):
                return

            self.click_to('template_stash')

            if self.stop():
                raise TimeoutError("Не смог открыть стеш")
            else:
                time.sleep(.5)

    # endregion

    # region Выход из ПОЕ на перерыв
    def close_poe(self):
        window_name = "Path of Exile"
        while True:
            if self.stop():
                return f"Не смог закрыть окно {window_name}"

            time.sleep(3)

            hwnd = win32gui.FindWindow(None, window_name)
            if hwnd:
                win32gui.SetForegroundWindow(hwnd)  # Выводим на передний план окно

                keyboard.send("alt+f4")  # Закрываем его
            else:
                return

    # endregion

    # region Продажа. Ожидание очереди сделок
    def wait_trade_info(self):
        while self.swag['chaos'] == 0 and self.swag['divine'] == 0:
            if self.stop():
                raise TimeoutError("Не дождался инфы о валюте в стеше")

        while self.divine_price == 0:
            if self.stop():
                raise TimeoutError("Не дождался инфы о цене дивайна")

        while not self.deals:
            if self.stop():
                raise TimeoutError("Не дождался инфы о сделках")

    # endregion

    # region Продажа. Запрос сделки
    def set_current_deal(self):
        if not self.deals:  # Если нет некст сделки, очищаем поля текущей, чтоб не висело
            self.current_deal = {
                'id': "",
                'character_name': "",
                'available_item_stock': 0,
                'exchange_currency': "chaos",
                'exchange_amount': 0,
                'item_currency': "",
                'item_amount': 0,
                'profit': 0,
                'image': "",
            }

        current_deal = self.deals.pop(0)

        # TODO: очень временно тут, доп проверка дублирует из другого места, щас баг (в телеге скрин)
        while self.deal_completed(current_deal['id']):
            current_deal = self.deals.pop(0)

        available_c = self.swag['chaos'] + self.swag['divine'] * self.divine_price

        item_setting = self.db.get_items(current_deal['item_currency'])
        max_qty = item_setting[0]['max_qty'] if item_setting else 0  # Сколько в заказе еще нужно докупить

        deal_item_amount = 0
        deal_exchange_amount = 0
        while deal_item_amount + current_deal['item_amount'] <= max_qty \
                and deal_item_amount + current_deal['item_amount'] <= current_deal['available_item_stock'] \
                and deal_exchange_amount + current_deal['exchange_amount'] <= available_c:
            deal_item_amount += current_deal['item_amount']
            deal_exchange_amount += current_deal['exchange_amount']

        if deal_item_amount == 0:
            return f"Количество для покупки: 0. ID сделки: {current_deal['id']}"

        current_deal.update({'divine_qty': deal_exchange_amount // self.divine_price,
                             'chaos_qty': deal_exchange_amount % self.divine_price})

        current_deal.update({'deal_item_amount': deal_item_amount, 'deal_exchange_amount': deal_exchange_amount})

        current_deal['whisper'] = current_deal['whisper'].format(
            current_deal['item_whisper'].format(current_deal['deal_item_amount']),
            current_deal['exchange_whisper'].format(current_deal['deal_exchange_amount']) if current_deal[
                                                                                                 'divine_qty'] == 0
            else "{0} Divine Orb and {1} Chaos Orb".format(current_deal['divine_qty'], current_deal['chaos_qty']))

        self.current_deal = current_deal

        self.update_deal_history(
            id=current_deal['id'],
            character_name=current_deal['character_name'],
            item=current_deal['item_currency'],
            qty=current_deal['deal_exchange_amount'],
            c_price=current_deal['c_price'],
            profit=current_deal['profit'],
        )

    def update_deal_history(self, **kwargs):
        self.deal_history.update(kwargs)

    def deal_completed(self, deal_id):
        return deal_id in self.db.get_last_deals(100)

    def request_deal(self):
        time.sleep(.5)

        self.send_to_chat(self.current_deal['whisper'])

        self.click_to('template_accept', timeout=self.v('party_timeout'))

    def take_currency(self):

        if self.stop():
            raise TimeoutError("Не смог взять валюту из стеша")

        self.open_stash()

        self.currency_put_in()

        self.open_currency_tab()  # Нажимаем на валютную вкладку
        self.currency_from_stash(self.current_deal['divine_qty'], 'divine')
        self.currency_from_stash(self.current_deal['chaos_qty'], 'chaos')

    def currency_put_in(self, is_trade=False):
        region = self.v('region_inventory_fields')

        trade_template_settings = self.v('template_trade') if is_trade else None

        attempts = 3
        while attempts:

            self.close_x_tabs()

            time.sleep(1)
            cells_matrix = self.get_cells_matrix(region)
            non_empty_cells = list(zip(*np.where(cells_matrix == 0)))

            if not non_empty_cells:
                return

            non_empty_cells = sorted(non_empty_cells, key=itemgetter(1))

            pyautogui.keyDown('ctrl')
            for y, x in non_empty_cells:
                # if is_trade and x % 2 == 0 and not self.find_template(**trade_template_settings):
                #     # Проверка каждые 2 ряда (10 выкладываний), чтобы, если трейд отменился, пол не долбить
                #     raise AttributeError("Продавец отменил трейд")

                self.check_freeze()

                pyautogui.moveTo(int(region[0] + region[2] * (x + 0.5) / 12),
                                 int(region[1] + region[3] * (y + 0.5) / 5),
                                 .05)
                pyautogui.click()

            pyautogui.keyUp('ctrl')

            # При трейде валюта не исчезает из инвентаря. Проверяем, что в трейд-окне столько же занятых ячеек
            if is_trade:
                trade_cells_matrix = self.get_cells_matrix(self.v('region_trade_inventory_fields_my'))
                trade_non_empty_cells = list(zip(*np.where(trade_cells_matrix == 0)))
                if len(non_empty_cells) == len(trade_non_empty_cells):
                    return

            attempts -= 1

        raise TimeoutError(f"Не смог выложить валюту из инвентаря с 3 попыток")

    def get_cells_matrix(self, region, item=None):
        """
        Возвращает 2-мерную матрицу, где 0 - пустая ячейка, 1 - заполненная
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
        self.click_to('template_x_button', wait_template=False)

    def currency_from_stash(self, amount, currency):

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

        if stack < amount:
            raise ValueError(f"Недостаточно валюты '{currency}': всего {stack}, требуется {amount}")

        stack_size = 10
        inv_region = self.v('region_inventory_fields')

        if stack - amount == 0:
            pyautogui.moveTo(*currency_coord, random.uniform(.1, .2))
            pyautogui.keyDown('ctrl')
            pyautogui.click(clicks=(math.ceil(amount // stack_size)), interval=.2)
            pyautogui.keyUp('ctrl')

        else:
            pyautogui.moveTo(*currency_coord, .1)
            pyautogui.keyDown('ctrl')
            pyautogui.click(clicks=math.floor(amount // stack_size), interval=.2)
            pyautogui.keyUp('ctrl')
            if amount % stack_size != 0:
                cells_matrix = self.get_cells_matrix(inv_region)
                empty_cell = sorted(list(zip(*np.where(cells_matrix == 1))), key=itemgetter(1))[0]

                pyautogui.moveTo(*currency_coord, .1)
                pyautogui.keyDown('Shift')
                pyautogui.click()
                pyautogui.keyUp('Shift')
                pyautogui.write(f'{amount % stack_size}')
                pyautogui.press('Enter')
                pyautogui.moveTo(int(inv_region[0] + inv_region[2] * (empty_cell[1] + 0.5) / 12),
                                 int(inv_region[1] + inv_region[3] * (empty_cell[0] + 0.5) / 5),
                                 .1)
                time.sleep(.1)
                pyautogui.click()

        counted = self.count_items(inv_region, currency)
        if amount == counted:
            return
        else:
            raise ValueError(f"Выложил неверное количество валюты. Нужно: {amount}, подсчитано: {counted}")

    def count_items(self, region, item):
        self.close_x_tabs()

        cells_matrix = self.get_cells_matrix(region, item)
        cells = list(zip(*np.where(cells_matrix == 1)))

        pyautogui.moveTo(1, 1)
        inventory = np.array(pyautogui.screenshot(region=region))
        h = inventory.shape[0] / 5
        w = inventory.shape[1] / 12
        qty = 0

        for y, x in cells:
            _qty = image_to_int(inventory[int(y * h): int((y + .4) * h), int(x * w): int((x + .5) * w)], 150)
            if _qty == 0:  # На предметах, где максимальный стак - 1, нет вообще цифр
                _qty = 1

            qty += _qty

        # if self.app.s(self.key, 'debug'):
        print(f"Подсчитано {item}: {qty}")

        return qty

    def teleport(self):
        self.send_to_chat(f"/hideout {self.current_deal['character_name']}")
        time.sleep(2)
        self.wait_for_template('template_game_loaded')  # Ждем загрузку

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
                raise TimeoutError("Не дождался трейда")

        self.clear_logs()

    def put_currency(self):
        self.currency_put_in(True)

    def check_items(self):
        qty = 0
        region = self.v('region_trade_inventory_fields_seller')
        while self.current_deal['deal_item_amount'] > qty:
            self.activate_items(region)

            qty = self.count_items(region, self.current_deal['item_currency'])

            if self.stop():
                raise TimeoutError(
                    f"Неверное количество предметов для сделки {qty} (нужно {self.current_deal['deal_item_amount']})")

    def activate_items(self, region):
        cells_matrix = self.get_cells_matrix(region)
        non_empty_cells = list(zip(*np.where(cells_matrix == 0)))

        for y, x in non_empty_cells:
            self.check_freeze()
            pyautogui.moveTo(int(region[0] + region[2] * (x + 0.5) / 12),
                             int(region[1] + region[3] * (y + 0.5) / 5),
                             .1)

    def set_complete_trade(self):
        try:
            if self.wait_for_template('template_cancel_complete_trade', .1, accuracy=.8):
                # Уже нажата кнопка (т.к. вместо нее появилась кнопка отмены трейда)
                return
        except TimeoutError:
            pass

        self.click_to('template_complete_trade', accuracy=.8)

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

    def say_ty(self):
        self.ty(self.current_deal['character_name'])
        self.send_to_chat(f"/kick {self.v('bot_name')}")

        self.update_deal_history(deal_time=int(datetime.now().timestamp()) - self.deal_history['date'],
                                 completed=True)
        self.db.change_item_qty(self.current_deal['item_currency'], -self.current_deal['deal_item_amount'])

    def clear_logs(self):
        open(self.v('logs_path'), 'w').close()  # Очистка логов перед трейдом

    def get_trade_status(self):
        with open(self.v('logs_path'), 'r', encoding="utf-8") as f:
            for line in f:
                if 'Trade accepted.' in line:
                    return 'accepted'
                elif 'Trade cancelled.' in line:
                    return 'cancelled'

# endregion