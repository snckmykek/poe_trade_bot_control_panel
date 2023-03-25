import inspect
import json
import math
import os
import random
import threading
import time
import traceback
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

from bots.bot import Coord, Simple, Template, get_window_param, to_global
from bots.common import DealPOETrade
from bots.poe.poe_base import PoeBase
from bots.poe.seller.additional_functional import SellerContent
from bots.poe.seller.db_requests import Database
from bots.poe.poe_stash_api import stash
from errors import StopStepError, SettingsNotCompletedError


class PoeSeller(PoeBase):
    # Обязательные
    icon = 'account-arrow-left'
    name = "ПОЕ: Продавец"
    key = "poe_seller"

    # Кастомные
    STASH_CELL_SIZE: float = 47.2
    characters_in_area = ListProperty([])
    current_deal: DealPOETrade = DealPOETrade()
    current_deal_dict: dict = DictProperty(dict(DealPOETrade.__dict__))
    chaos_price: float = NumericProperty()
    divine_price: float = NumericProperty()
    db: Database
    deals = ListProperty([])
    trade_chat_thread: threading.Thread = None
    trade_state: str = 'not_finished'  # cancelled, accepted

    # region init
    def __init__(self):
        super(PoeSeller, self).__init__()

        self.set_task_tab_buttons()
        self.set_tasks()
        self.set_windows()

        self.db = Database(os.path.join(self.app.db_path, f"{self.key}.db"))

        Clock.schedule_once(self.delayed_init)

    def set_task_tab_buttons(self):
        self.task_tab_buttons.extend(
            [
                {
                    'text': "Заглушка",
                    'icon': 'alert-box-outline',
                    'func': self.stub
                },
            ]
        )

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
                ]
            },
            {
                'name': "Запуск потока анализа чата и подготовка к торговле",
                'timer': 20,
                'available_mode': 'after_start',
                'stages': [
                    {
                        'func': self.load_stash_info,
                        'name': "Телепорт в ХО и обновление товаров на продажу"
                    },
                    {
                        'func': self.start_chat_thread,
                        'name': "Запросить цены валюты и запустить поток анализа чата"
                    },
                ]
            },
            {
                'name': "Подготовка к сделке",
                'timer': 60,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.wait_deals,
                        'on_error': {'goto': (2, 0)},
                        'name': "Ожидание сделок"
                    },
                    {
                        'func': self.stub,
                        'name': "Подготовка служебных данных"
                    },
                    {
                        'func': self.set_current_deal,
                        'on_error': {'goto': (2, 0)},
                        'name': "Подобрать и установить текущую сделку"
                    },
                    {
                        'func': self.take_items,
                        'name': "Взять товар"
                    },
                ]
            },
            {
                'name': "Сделка",
                'timer': 180,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.invite_trade,
                        'name': "Кинуть трейд"
                    },
                    {
                        'func': self.put_items,
                        'name': "Выложить товар",
                        'on_error': {'goto': (3, 0)}
                    },
                    {
                        'func': self.check_currency,
                        'name': "Проверить валюту",
                        'on_error': {'goto': (3, 0)}
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
                        'on_error': {'goto': (3, 0)},
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
                    key='POESESSID',
                    name="Кука POESESSID от акка, дл запроса ину по стешу",
                    type='str'
                ),
            ],

            'Общие настройки': [
                Simple(
                    key='logs_path',
                    name="Путь до логов ПОЕ",
                    type='str'
                ),
                Simple(
                    key='max_attempts',
                    name="Максимальное число попыток, чтобы взять/выложить валюту",
                    type='int'
                ),
                Simple(
                    key='button_delay_ms',
                    name="Дополнительная задержка после действий мыши и клавиатуры (ms)",
                    type='int'
                ),
                Simple(
                    key='chat_update_frequency',
                    name="Частота обновления инфы из чата (из файла Client.txt) в сек",
                    type='int'
                ),
                Simple(
                    key='price_tolerance',
                    name="Допустимое отклонение от цены (при конвертации дивайнов в хаосы), в %",
                    type='int'
                ),
            ],
            'Окно: Path of Exile (игра)': [
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
                    key='region_stash_fields',
                    name="Поле ячеек вкладки стеша (как можно точнее по краю внешних ячеек дефолтной вкладки)",
                    relative=True,
                    snap_mode='lt',
                    type='region',
                    window='poe'
                ),
                Coord(
                    key='coords_tabs',
                    name="Координаты вкладок слева-направо (на каждую - 1 клик, без папок. Можно списком справа)",
                    relative=True,
                    snap_mode='lt',
                    type='coord_list',
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
                    name="Поле ячеек трейда (покупателя)",
                    relative=True,
                    snap_mode='ct',
                    type='region',
                    window='poe_except_inventory'
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
            'poe_except_inventory': {'name': "Path of Exile", 'expression': ('x', 'y', 'int(w - 0.6166 * h)', 'h')}

        }

    def delayed_init(self, *_):
        self.task_tab_content = SellerContent()
        self.app.add_task_content()
        self.set_variables_setting()

    # endregion

    # region Запуск потока анализа чата и подготовка к торговле
    def start_chat_thread(self):
        if not self.trade_chat_thread or not self.trade_chat_thread.is_alive():
            self.trade_chat_thread = threading.Thread(target=lambda *_: self.chat_loop(), daemon=True)
            self.trade_chat_thread.start()

    def chat_loop(self):
        self.update_currency_price()

        while True:
            if self.app.need_break:
                return

            self.check_freeze()

            _start = datetime.now()

            try:
                self.check_chat()
            except Exception as e:
                self.print_log(f"Ошибка в получении инфы из чата.\n" + str(e) + "\n" + traceback.format_exc())

            _interval = self.v('chat_update_frequency') - (datetime.now() - _start).total_seconds()
            if _interval > 0:
                time.sleep(_interval)

    def update_currency_price(self):
        self.chaos_price = self.get_item_price("chaos", "divine")
        self.divine_price = round(self.get_item_price("divine", "chaos"))

        if not self.chaos_price or not self.divine_price:
            raise StopStepError("Не удалось получить курс валют")

    def get_item_price(self, item, currency):

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
            "Cookie": f"POESESSID={self.v('POESESSID')}"
        }

        # Ссылка для запроса к странице с балком
        url = fr"https://www.pathofexile.com/api/trade/exchange/{league}"

        # Запрос поиска
        data = {
            "query": {
                "status": {
                    "option": "online"
                },
                "want": [currency, ],
                "have": [item, ],
                "minimum": 1

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

        prices = []
        for deal_id, deal_info in results.items():
            offer_info = deal_info['listing']['offers'][0]

            price_per_each = offer_info['item']['amount'] / offer_info['exchange']['amount']
            prices.append(price_per_each)

        sorted(prices, reverse=True)

        avg = sum(prices) / len(prices)

        # Вырезаем прайсфиксерные цены
        _prices = prices.copy()
        for _price in _prices:
            if abs((_price - avg) / avg) > 0.05:  # При отклонении больше чем на 5% от среднего - убираем из списка
                prices.remove(_price)  # Удаляет первый совпавший элемент
                avg = sum(prices) / len(prices)  # Пересчет среднеарифметического

        return sum(prices) / len(prices)

    def check_chat(self):
        with open(self.v('logs_path'), 'r+', encoding="utf-8") as f:
            lines = f.read().splitlines()
            f.truncate(0)  # Очистка файла

        for line in lines:
            if "@From" in line:
                self.parse_msg(line)
            elif "has joined the area" in line:
                self.character_joined_area(line)
            elif "has left the area" in line:
                self.character_left_area(line)
            elif "Trade cancelled." in line:
                self.trade_state = 'cancelled'
            elif "Trade accepted." in line:
                self.trade_state = 'accepted'
            elif "AFK mode is now ON." in line:
                self.off_afk_mode()

    def parse_msg(self, line):
        character, msg = line.split("@From ")[1].split(': ', maxsplit=1)

        if self.is_trade_request(msg):
            self.add_deal_by_trade_request(character, msg)
        else:
            self.process_notrade_msg(character, msg)

    def is_trade_request(self, msg):
        return "Hi, I'd like to buy your " in msg

    def add_deal_by_trade_request(self, character, trade_request):
        if self.party_is_full():
            return

        deal_info = self.parse_trade_request(trade_request)
        deal_info.update({'character_name': character})

        if self.deal_already_added(deal_info):
            return

        item_info = self.get_item_info(deal_info['item_name'], deal_info['position'])

        if self.wrong_price(deal_info, item_info):
            return

        deal_info = self.precise_qty_deal_info(deal_info, item_info)

        if deal_info['item_qty'] == 0:
            self.send_to_chat(f"@{character} sold")
            return
        elif deal_info['reply_whisper']:
            self.send_to_chat(deal_info['reply_whisper'])

        deal_info.update({'image': item_info['icon']})
        deal_info.update({'item_stock': item_info['qty']})
        deal_info.update({'item_stack_size': item_info['stack_size']})
        deal_info.update({'item_tab_number': item_info['tab_number']})
        deal_info.update({'item_coords': self.adapted_item_coords([item_info['x'], item_info['y']])})

        self.add_deal(deal_info)

    def adapted_item_coords(self, coords):
        _x = coords[0]
        _y = coords[1]
        _default_stash_size = 566

        stash_region = self.v('region_stash_fields')
        x_coef = stash_region[2] / _default_stash_size
        y_coef = stash_region[3] / _default_stash_size

        return to_global(stash_region, [_x * x_coef, _y * y_coef])

    def party_is_full(self):
        pass

    def parse_trade_request(self, trade_request):
        trade_request_remainder = trade_request.split("Hi, I'd like to buy your ")[1]

        item_part, trade_request_remainder = trade_request_remainder.split(" for my ")
        currency_part, trade_request_remainder = trade_request_remainder.split(" in ")
        position = self.get_position(trade_request_remainder)

        item_qty, item_name = item_part.split(" ", maxsplit=1)
        currency_qty, currency = currency_part.split(" ", maxsplit=1)

        return {
            'item_name': item_name,
            'item_qty': int(item_qty),
            'currency': currency,
            'currency_qty': int(currency_qty),
            'position': position,
            'trade_request': trade_request,
            'reply_whisper': ""
        }

    def deal_already_added(self, deal_info):
        for deal in self.deals:
            if (deal_info['character_name'] == deal.character_name
                    and deal_info['item_name'] == deal.item_name
                    and deal_info['item_qty'] == deal.item_qty):
                return True

        return False

    def get_item_info(self, item_name, position):
        item_info_row = self.db.get_item_info(item_name, position)
        item_info = dict(item_info_row)

        if not item_info['is_layout']:
            col, row = map(int, item_info['cell_id'].split(","))
            item_info['x'], item_info['y'] = col * self.STASH_CELL_SIZE, row * self.STASH_CELL_SIZE

        # TODO В currency хранится айди предмета. Надо добавить таблицу с предметами и брать Имя валюты по айди
        if item_info['currency'] == "chaos":
            item_info['currency'] = "Chaos Orb"
        elif item_info['currency'] == "divine":
            item_info['currency'] = "Divine Orb"

        return item_info

    def wrong_price(self, deal_info, item_info):
        if deal_info['currency'] != item_info['currency']:
            return True

        # TODO добавить проверку кратности количества и цены

        return False

    def precise_qty_deal_info(self, deal_info, item_info):
        if deal_info['item_qty'] < item_info['qty'] and deal_info['item_qty'] % item_info['min_qty'] == 0:
            return deal_info

        qty_packages = \
            math.floor(min(item_info['qty'], deal_info['item_qty']) // item_info['min_qty'])
        qty = qty_packages * item_info['min_qty']
        price = qty_packages * item_info['price_for_min_qty']
        currency = item_info['currency']

        deal_info['item_qty'] = qty
        deal_info['currency_qty'] = price
        deal_info['reply_whisper'] = f"@{deal_info['character_name']} {qty} left for {price} {currency}"

        return deal_info

    def add_deal(self, deal_info):
        deal = DealPOETrade()
        deal.character_name = deal_info['character_name']
        deal.currency = deal_info['currency']

        if deal_info['currency'] == "Divine Orb":
            deal.divine_qty = deal_info['currency_qty']
        elif deal_info['currency'] == "Chaos Orb":
            deal.chaos_qty = deal_info['currency_qty']
        else:
            self.print_log(f"Неверная валюта сделки: {deal_info['currency']}")
            return

        deal.item_name = deal_info['item_name']
        deal.item_qty = deal_info['item_qty']

        deal.image = deal_info['image']
        deal.item_stock = deal_info['item_stock']
        deal.item_stack_size = deal_info['item_stack_size']
        deal.item_tab_number = deal_info['item_tab_number']
        deal.item_coords = deal_info['item_coords']

        self.invite_party(deal_info['character_name'])

        self.change_item_qty(deal_info['item_name'], deal_info['position'])

        self.deals.append(deal)

    def invite_party(self, character_name):
        self.send_to_chat(f"/invite {character_name}")

    def get_position(self, trade_request_remainder: str):
        if "(" in trade_request_remainder:
            trade_request_remainder = trade_request_remainder.split('stash tab "')[1]
            tab, trade_request_remainder = trade_request_remainder.rsplit('"; position: left ', maxsplit=1)
            col, trade_request_remainder = trade_request_remainder.split(", top ")
            row = trade_request_remainder.split(")")[0]

            return {'tab': tab, 'col': int(col), 'row': int(row)}
        else:
            # Это недефолтная вкладка, позиция не указывается, она однозначна
            return None

    def process_notrade_msg(self, character, msg):
        # change 2d/div, offer, etc.. else отправить в телегу оповещение/записать лог о "странном" сообщении
        pass

    def character_joined_area(self, line):
        character = line.split(" has joined the area")[0].split(" : ")[1]
        self.characters_in_area.append(character)

    def character_left_area(self, line):
        character = line.split(" has left the area")[0].split(" : ")[1]

        try:
            self.characters_in_area.remove(character)
        except ValueError:
            pass

    def off_afk_mode(self):
        self.send_to_chat("/afkoff")

    # endregion

    def update_current_deal_dict(self):
        # Аттрибуты объекта в виде словаря (кроме функций, методов и __x__), типа .__dict__, но надежнее
        self.current_deal_dict = dict((k, v) for k, v in inspect.getmembers(self.current_deal) if
                                      not inspect.isfunction(v) and not inspect.ismethod(v) and not inspect.isbuiltin(
                                          v) and k[:2] != '__')

    def change_item_qty(self, item_name, position, qty):
        pass

    # region Получение инфы по стешу
    def load_stash_info(self):
        tabs = stash.fetch_all_tabs(self.v('league'), 'pc', self.v('account_name'), self.v('POESESSID'))

        self.db.clear_cells_info()
        self.db.clear_items()

        for tab_number, tab in enumerate(tabs):
            print('========')
            is_layout = False
            for key in tab.keys():
                if "Layout" in key:
                    is_layout = True
                    self.save_cells_info(tab_number, key, tab[key]['layout'])

            items = tab.get('items')
            self.save_items_in_tab(tab_number, items, is_layout)

    def save_cells_info(self, tab_number, tab_type, layout):
        print(tab_number, tab_type, layout)
        cells_info = [
            (tab_number, tab_type, cell_id, cell_info.get('section', ""), cell_info['x'], cell_info['y'])
            for cell_id, cell_info in layout.items()
        ]
        self.db.save_cells_info(cells_info)

    def save_items_in_tab(self, tab_number, items, is_layout=False):
        print(tab_number, items)
        items_info = []

        for item in items:
            qty = 1
            stack_size = 1
            properties = item.get('properties', [])
            for prop in properties:
                if prop.get('name') == 'Stack Size':
                    values = prop.get('values')
                    if values:
                        qty, stack_size = map(int, values[0][0].split('/'))

            price_for_min_qty, min_qty, currency = self.price_from_note(item.get('note'))

            item_info = (
                tab_number,
                ",".join([str(item['x']), str(item['y'])]) if item['y'] else str(item['x']),
                is_layout,
                "",
                item['baseType'],
                item['typeLine'],
                item['baseType'],
                item['w'],
                item['h'],
                item['icon'].split("https://web.poecdn.com")[1],
                qty,
                stack_size,
                min_qty,
                price_for_min_qty,
                currency,
                item['identified'],
                item['ilvl']
            )

            items_info.append(item_info)

        self.db.save_items(items_info)

    def price_from_note(self, note):
        if not note or "price " not in note:
            return 0, 1, ""

        price_part, currency = note.split("price ")[1].split(" ")

        if "/" in price_part:
            price_for_min_qty, min_qty = price_part.split("/")
        else:
            price_for_min_qty, min_qty = price_part, 1

        return price_for_min_qty, min_qty, currency

    # endregion

    # region Подготовка к сделке

    def deal_is_available(self, deal):
        return deal.character_name in self.characters_in_area

    def wait_deals(self):
        while True:
            for deal in self.deals:
                if self.deal_is_available(deal):
                    return

            time.sleep(1)

            if self.stop():
                raise StopStepError("Нет сделок")

    def set_current_deal(self):

        next_deal = self.pop_next_available_deal()

        if next_deal is not None:
            self.trade_state = 'not_finished'
            self.current_deal = next_deal
            self.update_current_deal_dict()
        else:
            raise StopStepError("Нет следующей сделки")

    def pop_next_available_deal(self):
        for i, deal in enumerate(self.deals):
            if self.deal_is_available(deal):
                return self.deals.pop(i)

        return None

    def clear_return_current_deal(self):
        # TODO Если трейд сорвался, что что делать со сделкой? Еще раз пытаться сразу или добавить обратно в очередь?
        last_deal = self.current_deal

        if last_deal.character_name in self.characters_in_area and self.trade_state != 'accepted':
            self.deals.insert(0, last_deal)

    def take_items(self):
        self.open_stash()

        self.clear_inventory()

        self.from_stash_to_inventory(self.current_deal.item_qty, self.current_deal.item_name,
                                     self.current_deal.item_stack_size, self.current_deal.item_stock)

    def get_item_coord_and_qty(self, item):
        item_coord = self.current_deal.item_coords
        tab_number = self.current_deal.item_tab_number

        item_qty_in_cell = self.get_items_qty_in_cell(item_coord, item_name=item)
        while not item_qty_in_cell:
            self.try_to_open_tab(tab_number)
            item_qty_in_cell = self.get_items_qty_in_cell(item_coord, item_name=item)

            if self.stop():
                raise StopStepError("Не смог открыть валютную вкладку")

        return item_coord, item_qty_in_cell

    def try_to_open_tab(self, tab_number):
        try:
            self.mouse_move_and_click(*self.v('coords_tabs')[tab_number], clicks=1, duration=.15, sleep_after=.15)
        except IndexError:
            raise SettingsNotCompletedError(f"Не все координаты вкладок указаны")

    def get_item_image(self, item):
        return self.current_deal.image

    # endregion

    # region Сделка

    def invite_trade(self):
        if self.find_template('template_trade'):
            return

        self.send_to_chat(f"/tradewith {self.current_deal.character_name}")

        self.wait_for_template('template_trade')

    def put_items(self):
        self.from_inventory_to_trade()

    def check_currency(self):
        region = self.v('region_trade_inventory_fields_his')

        while True:

            if not self.find_template('template_trade'):
                raise StopStepError("Трейд закрылся до завершения")

            divine_qty = self.count_items(region, "Divine Orb")
            # Для случаев покупок за дивайны, очень часто будет всё четко, лишние действия не делаем
            if self.current_deal.currency == "Divine Orb" \
                    and self.current_deal.divine_qty and divine_qty >= self.current_deal.divine_qty:
                return

            chaos_qty = self.count_items(region, "Chaos Orb")
            # Для случаев покупок за хаосы, очень часто будет всё четко, лишние действия не делаем
            if self.current_deal.currency == "Chaos Orb" \
                    and self.current_deal.chaos_qty and chaos_qty >= self.current_deal.chaos_qty:
                return

            # Остается случай, когда покупатель скинул пасту с одной валютой, а дает другую - считаем по курсу
            if self.enough_currency_qty(divine_qty, chaos_qty):
                return

            if self.stop():
                raise StopStepError(
                    f"Неверное количество предметов для сделки {qty} (нужно {self.current_deal.item_qty})")

    def enough_currency_qty(self, divine_qty, chaos_qty):
        def chaos_qty_from_divine_qty(_divine_qty):
            return round(_divine_qty * (1/self.chaos_price))

        return (chaos_qty_from_divine_qty(divine_qty) + chaos_qty) * (1 - self.v('price_tolerance')/100) >= \
            chaos_qty_from_divine_qty(self.current_deal.divine_qty) + self.current_deal.chaos_qty

    def set_complete_trade(self):
        if self.find_template('template_cancel_complete_trade', accuracy=.8):
            # Уже нажата кнопка (т.к. вместо нее появилась кнопка отмены трейда)
            return

        self.click_to('template_complete_trade', accuracy=.8)

    # endregion

    # region Дождаться завершения трейда

    def wait_confirm(self):
        while True:
            if self.trade_state == 'accepted':
                return
            elif self.trade_state == 'cancelled':
                raise StopStepError("Трейд отменен продавцом")

            if self.stop():
                raise StopStepError("Не дождался подтверждения от продавца")

            time.sleep(.5)

    def on_complete_trade(self):
        self.say_ty()
        self.leave_party()

        self.current_deal = DealPOETrade()

    def say_ty(self):
        self.send_to_chat(f"@{self.current_deal.character_name} ty")

    def leave_party(self):
        self.send_to_chat(f"/kick {self.current_deal.character_name}")

    # endregion

