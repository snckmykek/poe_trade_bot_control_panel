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
from textwrap import dedent

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
from bots.common import DealPOETrade, CustomDialog
from bots.poe.poe_base import PoeBase
from bots.poe.seller.additional_functional import SellerContent, TabsManager
from bots.poe.seller.db_requests import Database
from bots.poe.poe_stash_api import stash
from controllers import mouse_controller
from errors import StopStepError, SettingsNotCompletedError, BotDevelopmentError


class PoeSeller(PoeBase):
    # Обязательные
    icon = 'account-arrow-right'
    name = "ПОЕ: Продавец"
    key = "poe_seller"

    # Кастомные
    STASH_CELL_SIZE: float = 47.2
    MAX_TRADE_INVITE_NUMBER: int = 5
    cancel_any_requests_thread: threading.Thread = None
    characters_in_area = ListProperty([])
    current_deal: DealPOETrade = DealPOETrade()
    current_deal_dict: dict = DictProperty(dict(DealPOETrade.__dict__))
    chaos_price: float = NumericProperty()
    divine_price: float = NumericProperty()
    db: Database
    deals = ListProperty([])
    trade_chat_thread: threading.Thread = None
    trade_state: str = 'not_finished'  # cancelled, accepted
    trade_invite_number: int = 0
    start_deal_timestamp: int = 0
    _last_telegram_msg_timestamp: int = 0

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
                    'text': "Менеджер вкладок",
                    'icon': 'alert-box-outline',
                    'func': self.open_tabs_manager
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
                        'func': self.start_chat_thread,
                        'name': "Запросить цены валюты и запустить поток анализа чата"
                    },
                ]
            },
            {
                'name': "Подсчет итемов в стеше на продажу",
                'timer': 300,
                'available_mode': 'after_start',
                'stages': [
                    {
                        'func': self.check_stash_info,
                        'name': "Посчитать итемы на продажу"
                    },
                ]
            },
            {
                'name': "Ожидание сделок",
                'timer': 60,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.wait_deals,
                        'on_error': {'goto': (3, 0)},
                        'name': "Ожидание сделок"
                    },
                ]
            },
            {
                'name': "Подготовка к сделке",
                'timer': 60,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.prepare_service,
                        'name': "Подготовка служебных данных"
                    },
                    {
                        'func': self.set_current_deal,
                        'on_error': {'goto': (3, 0)},
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
                'timer': 90,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.invite_trade,
                        'name': "Кинуть трейд",
                        'on_error': {'func': lambda result: self.on_error_trade(result),
                                     'goto': (3, 0)}
                    },
                    {
                        'func': self.put_items,
                        'name': "Выложить товар",
                        'on_error': {'goto': (5, 0)}
                    },
                    {
                        'func': self.check_currency,
                        'name': "Проверить валюту",
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
                'timer': 10,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.wait_confirm,
                        'on_error': {'goto': (5, 0)},
                        'name': "Дождаться завершения трейда",
                        'on_complete': {'func': lambda result: self.save_current_deal_result(result, 'completed')}
                    },
                ]
            },
            {
                'name': "Действия после трейда",
                'timer': 30,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.on_complete_trade,
                        'on_error': {'goto': (5, 0)},
                        'name': "Кик из пати и запись валюты в БД"
                    },
                    {
                        'func': self.clear_inventory,
                        'on_error': {'goto': (5, 0)},
                        'name': "Очистить инвентарь"
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
                Simple(
                    key='proxy',
                    name="Прокси, как на компе для игры в ПОЕ (если нет прокси, указать 0)",
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
                Simple(
                    key='deal_lifetime',
                    name="Сколько сделка будет висеть в списке (в сек)",
                    type='int'
                ),
                Simple(
                    key='telegram_bot_token',
                    name="Токен бота, от чьего имени будет отправляться сообщение в чаты (должен быть админом в чате)",
                    type='str'
                ),
                Simple(
                    key='telegram_chat_ids',
                    name="Список ID чатов телеграм через запятую, для рассылки ошибок бота",
                    type='str'
                ),
                Simple(
                    key='user_name',
                    name="Имя пользователя (Используется при рассылке в телегу об ошибках)",
                    type='str'
                ),
                Simple(
                    key='party_max_size',
                    name="Сколько максимум одновременных трейдов можно принимать (не больше 5 - фулл пати)",
                    type='int'
                ),
                Simple(
                    key='chaos_qty_notification',
                    name="Количество хаосов, при достижении которых оповещение в телегу",
                    type='int'
                ),
                Simple(
                    key='divine_qty_notification',
                    name="Количество дивайнов, при достижении которых оповещение в телегу",
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
                Simple(
                    key='tabs_names',
                    name="Названия вкладок слева-направо через запятую (без папок)",
                    type='str'
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
                    name="Кнопка 'ACCEPT' при запросе пати или трейда",
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
                    key='template_decline',
                    name="Кнопка 'DECLINE' при запросе пати или трейда",
                    region=Coord(
                        key='region_decline',
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
                    key='template_waiting_trade_request',
                    name="Кнопка 'CANCEL' при ожидании трейда после запроса",
                    region=Coord(
                        key='region_waiting_trade_request',
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

    def open_tabs_manager(self, *_):
        content = TabsManager()

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

    # endregion

    def on_stage_started_manually(self):
        self.clear_logs()

    # region Запуск потока анализа чата и подготовка к торговле
    def start_chat_thread(self):
        if not self.trade_chat_thread or not self.trade_chat_thread.is_alive():
            self.trade_chat_thread = threading.Thread(target=lambda *_: self.chat_loop(), daemon=True)
            self.trade_chat_thread.start()

    def chat_loop(self):
        self.update_currency_price()

        while True:
            if self.need_stop_threads():
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
        if self.v('proxy') != "0":
            proxies = {'https': f"http://{self.v('proxy')}"}
        else:
            proxies = None

        response_request = requests.post(url, headers=headers, json=data, proxies=proxies)
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

        prices = sorted(prices[:10], reverse=True)

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
        character_name, msg = line.split("@From ")[1].split(': ', maxsplit=1)
        character_name = self.character_name_without_clan(character_name)

        if self.is_trade_request(msg):
            self.add_deal_by_trade_request(character_name, msg)
        else:
            self.process_notrade_msg(character_name, msg)

    def character_name_without_clan(self, character_name):
        if ">" in character_name:
            return character_name.split("> ")[1]
        else:
            return character_name

    def is_trade_request(self, msg):
        return "like to buy your " in msg

    def add_deal_by_trade_request(self, character_name, trade_request):
        if self.party_is_full():
            self.print_log("Пати полное, сделка проигнорирована")
            return

        deal_info = self.get_deal_info(character_name, trade_request)

        self.add_deal(deal_info)

        Clock.schedule_once(lambda *_: self.invite_party(deal_info['character_name']), random.randint(1, 2))

        self.change_item_qty(deal_info['item_name'], -deal_info['item_qty'], deal_info['position'])

    def get_deal_info(self, character_name, trade_request):
        deal_info = self.parse_trade_request(trade_request)
        deal_info.update({'character_name': character_name})

        if self.deal_already_added(deal_info):
            self.print_log(f"Сделка с {character_name} уже в списке, кидаю пати еще раз")
            self.invite_party(character_name)
            return

        item_info = self.get_item_info_from_db(deal_info['item_name'], deal_info['position'])

        if self.wrong_price(deal_info, item_info):
            self.print_log(f"Цена в виспере указана неверно по итему: {deal_info['item_name']}, пропускаю")
            return

        deal_info = self.precise_qty_deal_info(deal_info, item_info)

        if deal_info['item_qty'] == 0:
            Clock.schedule_once(lambda *_: self.send_to_chat(f"@{character_name} sold"), 2)
            return
        elif deal_info['reply_whisper']:
            Clock.schedule_once(lambda *_: self.send_to_chat(deal_info['reply_whisper']), 3)

        deal_info.update({'image': item_info['icon']})
        deal_info.update({'item_stock': item_info['qty']})
        deal_info.update({'item_stack_size': item_info['stack_size']})
        deal_info.update({'item_tab_number': item_info['tab_number']})
        deal_info.update({'item_coords': self.adapted_item_coords([item_info['x'], item_info['y']])})
        deal_info.update({'item_info': item_info})

        return deal_info

    def adapted_item_coords(self, coords):
        _x = coords[0]
        _y = coords[1]
        _default_stash_size = 566

        indent = _default_stash_size / 12 / 2  # Отступ в пол ячейки

        stash_region = self.v('region_stash_fields')
        x_coef = stash_region[2] / _default_stash_size
        y_coef = stash_region[3] / _default_stash_size

        return to_global(stash_region, [(_x + indent) * x_coef, (_y + indent) * y_coef])

    def party_is_full(self):
        return len(self.deals) >= self.v('party_max_size')

    def parse_trade_request(self, trade_request):
        trade_request_remainder = trade_request.split("like to buy your ")[1]

        is_bulk = " listed for " not in trade_request_remainder

        if is_bulk:
            item_part, trade_request_remainder = trade_request_remainder.split(" for my ")
        else:
            item_part, trade_request_remainder = trade_request_remainder.split(" listed for ")
        currency_part, trade_request_remainder = trade_request_remainder.split(" in ")
        position = self.get_position(trade_request_remainder)

        if is_bulk:
            item_qty, item_name = item_part.split(" ", maxsplit=1)
        else:
            item_qty, item_name = 1, item_part.replace(",", "")
        currency_qty, currency = currency_part.split(" ", maxsplit=1)

        if currency == "Chaos Orb":
            currency = "chaos"
        elif currency == "Divine Orb":
            currency = "divine"

        if currency != "chaos" and currency != "divine":
            raise BotDevelopmentError(f"Для валюты: {currency} бот не разработан")

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

    def get_item_info_from_db(self, item_name, position):
        item_info_row = self.db.get_item_info(item_name, position)
        if item_info_row is None:
            error_message = f"Не найден предмет из запроса в чате: '{item_name}', pos: '{position}'"
            self.send_message_to_telegram(error_message)
            raise ValueError(error_message)

        item_info = dict(item_info_row)

        if not item_info['is_layout']:
            col, row = map(int, item_info['cell_id'].split(","))
            item_info['x'], item_info['y'] = col * self.STASH_CELL_SIZE, row * self.STASH_CELL_SIZE

        return item_info

    def wrong_price(self, deal_info, item_info):
        if deal_info['currency'] != item_info['currency']:
            return True

        return False

    def precise_qty_deal_info(self, deal_info, item_info):

        max_qty = math.floor(12 / item_info['w']) * math.floor(5 / item_info['h']) * item_info['stack_size']

        if deal_info['item_qty'] <= item_info['qty'] and deal_info['item_qty'] % item_info['min_qty'] == 0 \
                and deal_info['item_qty'] < max_qty:
            return deal_info

        qty_packages = math.floor(min(item_info['qty'], deal_info['item_qty']) // item_info['min_qty'])
        qty = math.floor(
            min(qty_packages * item_info['min_qty'], max_qty // item_info['min_qty'] * item_info['min_qty']))
        price = math.floor(qty / item_info['min_qty'] * item_info['price_for_min_qty'])
        currency = item_info['currency']

        deal_info['item_qty'] = qty
        deal_info['currency_qty'] = price
        deal_info['reply_whisper'] = f"@{deal_info['character_name']} {qty} left for {price} {currency}"

        return deal_info

    def add_deal(self, deal_info):
        deal = DealPOETrade()
        deal.character_name = deal_info['character_name']
        deal.currency = deal_info['currency']

        if deal_info['currency'] == "divine":
            deal.divine_qty = deal_info['currency_qty']
        elif deal_info['currency'] == "chaos":
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
        deal.position = deal_info['position']
        deal.item_info = deal_info['item_info']
        deal.added_timestamp = int(datetime.now().timestamp())

        self.deals.append(deal)

    def invite_party(self, character_name):
        self.send_to_chat(f"/invite {character_name}")

    def get_position(self, trade_request_remainder: str):
        if "(" in trade_request_remainder:
            trade_request_remainder = trade_request_remainder.split('stash tab "')[1]
            tab, trade_request_remainder = trade_request_remainder.rsplit('"; position: left ', maxsplit=1)
            col, trade_request_remainder = trade_request_remainder.split(", top ")
            row = trade_request_remainder.split(")")[0]

            return {'tab': tab, 'col': int(col) - 1, 'row': int(row) - 1}
        else:
            # Это недефолтная (layout) вкладка, позиция не указывается, она однозначна
            return None

    def process_notrade_msg(self, character, msg):
        if "change" in msg.lower():
            Clock.schedule_once(lambda *_: self.send_to_chat(f"@{character} have no change sry"), 2)
        elif "offer" in msg.lower():
            Clock.schedule_once(lambda *_: self.send_to_chat(f"@{character} no offer sry"), 2)
        elif "ty" in msg.lower() or "t4t" in msg.lower():
            pass
        else:
            self.send_message_to_telegram(
                self.msg_for_telegram_with_bot_name(
                    "Неопознанное сообщение от покупателя '{}':\n{}".format(character, msg)))

    def character_joined_area(self, line):
        character_name = line.split(" has joined the area")[0].split(" : ")[1]
        character_name = self.character_name_without_clan(character_name)
        self.characters_in_area.append(character_name)

    def character_left_area(self, line):
        character_name = line.split(" has left the area")[0].split(" : ")[1]
        character_name = self.character_name_without_clan(character_name)

        try:
            self.characters_in_area.remove(character_name)
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

    def change_item_qty(self, item_name, qty, position):
        self.db.change_item_qty(item_name, qty, position)

    # region Получение инфы по стешу
    def check_stash_info(self):

        self.db.clear_items()
        for tab in self.db.get_tabs_info():

            if not tab['use'] or tab['sections'] == 'skip':
                continue

            if tab['tab_layout'] == 'common':
                self.add_items_from_common_tab(tab)
            else:
                self.add_items_from_layout_tab(tab)

    def add_items_from_common_tab(self, tab):
        raise BotDevelopmentError("Для обычных вкладок не разработан механизм получения инфы по итемам")

    def add_items_from_layout_tab(self, tab):
        items_info_for_save = []

        for section in tab['sections'].split(","):
            self.try_to_open_tab(tab['tab_number'], tab['tab_layout'], section)

            for cell in self.get_cells_info(tab['tab_layout'], section):
                cell_coords = self.adapted_item_coords([cell['x'], cell['y']])
                item_info = self.get_item_info_by_ctrl_c(
                    [
                        'quantity_and_stacksize',
                        'item_name',
                        'typeLine',
                        'baseType',
                        'note',
                        'identified',
                        'ilvl',
                    ],
                    cell_coords
                )

                if not item_info:
                    continue

                price_for_min_qty, min_qty, currency = self.price_from_note(item_info.get('note', ""))

                item_info_for_save = (
                            tab['tab_number'],
                            tab['tab_name'],
                            cell['cell_id'],
                            True,
                            "",
                            item_info.get('item_name', ""),
                            item_info.get('typeLine', ""),
                            item_info.get('baseType', ""),
                            1,  # TODO: item['w']
                            1,  # TODO: item['h']
                            "",
                            item_info.get('quantity_and_stacksize', [0, 1])[0],
                            item_info.get('quantity_and_stacksize', [0, 1])[1],
                            min_qty,
                            price_for_min_qty,
                            currency,
                            item_info.get('identified', ""),
                            item_info.get('ilvl', ""),
                            item_info.get('note', "")
                )

                items_info_for_save.append(item_info_for_save)

        self.db.save_items(items_info_for_save)

    def get_cells_info(self, tab_layout, section):
        return self.db.get_cells_info(tab_layout, section)

    def load_stash_info(self):
        tabs = stash.fetch_all_tabs(self.v('league'), 'pc', self.v('account_name'), self.v('POESESSID'))

        self.db.clear_cells_info()
        self.db.clear_items()

        for tab_number, tab in enumerate(tabs):
            self.print_log('========')
            is_layout = False
            for key in tab.keys():
                if "Layout" in key:
                    try:
                        self.save_cells_info(tab_number, key, tab[key]['layout'])
                        is_layout = True
                    except Exception as e:
                        self.print_log("Ошибка при добавлении табы: {} - проигнорирована".format(
                            ",".join(map(str, [tab_number, key]))))
                        return

            items = tab.get('items')
            self.save_items_in_tab(tab_number, items, is_layout)

    def save_cells_info(self, tab_number, tab_type, layout):
        self.print_log("Добавляю лайаут вкладки: " + ", ".join(map(str, [tab_number, tab_type])))
        cells_info = [
            (tab_number, tab_type, cell_id, cell_info.get('section', ""), cell_info['x'], cell_info['y'])
            for cell_id, cell_info in layout.items()
        ]
        self.db.save_cells_info(cells_info)

    def save_items_in_tab(self, tab_number, items, is_layout=False):
        self.print_log(", ".join(map(str, [tab_number, "Итемы сохранены"])))
        items_info = []

        tabs_names = self.v('tabs_names').split(",")

        for item in items:
            qty = 1
            stack_size = 1
            properties = item.get('properties', [])
            for prop in properties:
                if prop.get('name') == 'Stack Size':
                    values = prop.get('values')
                    if values:
                        qty, stack_size = map(int, values[0][0].split('/'))

            note = item.get('note', "")
            price_for_min_qty, min_qty, currency = self.price_from_note(note)

            item_info = (
                tab_number,
                tabs_names[tab_number],
                ",".join([str(item['x']), str(item['y'])]) if not is_layout else str(item['x']),
                is_layout,
                "",
                item['name'] + (" " if item['name'] else "") + item['baseType'],
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
                item['ilvl'],
                note
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
            _deals = self.deals.copy()
            for deal in _deals:

                # Удаляем сделки, где продавец не пришел
                if int(datetime.now().timestamp()) - deal.added_timestamp > self.v('deal_lifetime'):
                    self.save_current_deal_result({'error': ""}, 'skipped')
                    self.change_item_qty(deal.item_name, deal.item_qty, deal.position)
                    self.deals.remove(deal)

                if self.deal_is_available(deal):
                    return

            time.sleep(1)

            if self.stop():
                raise StopStepError("Нет сделок")

    def prepare_service(self):

        self.trade_invite_number = 0
        self.start_deal_timestamp = int(datetime.now().timestamp())

        if not self.cancel_any_requests_thread or not self.cancel_any_requests_thread.is_alive():
            self.cancel_any_requests_thread = threading.Thread(target=lambda *_: self.cancel_any_requests(),
                                                               daemon=True)
            self.cancel_any_requests_thread.start()

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
                                     self.current_deal.item_stack_size, self.current_deal.item_stock,
                                     item_size=(self.current_deal.item_info['h'], self.current_deal.item_info['w']))

    def get_item_coord_and_qty(self, item):
        item_coord = self.current_deal.item_coords
        tab_number = self.current_deal.item_tab_number
        tab_type = self.current_deal.item_info['tab_type']
        section = self.current_deal.item_info['section']

        item_qty_in_cell = 0
        while not item_qty_in_cell:
            self.try_to_open_tab(tab_number, tab_type, section)
            _, item_qty_in_cell = self.get_item_and_qty_in_cell(item_coord)

            if self.stop():
                raise StopStepError("Не смог открыть валютную вкладку")

        return item_coord, item_qty_in_cell

    def try_to_open_tab(self, tab_number, tab_type, section):
        self.open_stash()
        try:
            self.mouse_move_and_click(
                *self.v('coords_tabs')[int(float(tab_number))], clicks=1, duration=.15, sleep_after=.15)
            self.open_section(tab_type, section)
        except IndexError:
            raise SettingsNotCompletedError(f"Не все координаты вкладок указаны")

    def open_section(self, tab_type, section):
        if section == '':  # На любой секции видно ячейки
            return

        stash_region = self.v('region_stash_fields')
        y = stash_region[1] + stash_region[3] / 12 / 2  # Половина первой клетки
        x0 = stash_region[0]
        w = stash_region[2]  # Ширина стеша
        if tab_type == 'fragmentLayout':
            if section == 'general':
                x = w * 1 / 8
            elif section == 'breach':
                x = w * 3 / 8
            elif section == 'scarab':
                x = w * 5 / 8
            elif section == 'maven' or section == 'eldritch':
                raise NotImplementedError("Не реализована продажа из вкладки eldritch/maven")

                # TODO: 1) балк запрос, но итемы лежат в разных ячейках, 2) сетка начинается от середины стешфилдс

                x = w * 7 / 8
                # Открываем секцию
                self.mouse_move_and_click(x, y, clicks=1, duration=.15, sleep_after=.15)

                y_additional = stash_region[1] + stash_region[3] * 5 / 12 / 2  # Половина 5 клетки
                x_additional = w * (3 if section == 'maven' else 5) / 8
                # Вложенная секция
                self.mouse_move_and_click(x_additional, y_additional, clicks=1, duration=.15, sleep_after=.15)

            else:
                raise BotDevelopmentError(f"Ошибка разработки бота. "
                                          f"Для типа '{tab_type}' секции '{section}' не указаны координаты")

        elif tab_type == 'currencyLayout':
            if section == 'general':
                x = w * 3 / 8
            elif section == 'influence':
                x = w * 5 / 8
            else:
                raise BotDevelopmentError(f"Ошибка разработки бота. "
                                          f"Для типа '{tab_type}' секции '{section}' не указаны координаты")

        else:
            raise BotDevelopmentError(f"Ошибка разработки бота. "
                                      f"Для типа '{tab_type}' не указаны координаты")

        self.mouse_move_and_click(x0 + x, y, clicks=1, duration=.15, sleep_after=.15)

    def get_item_image(self, item):
        return self.current_deal.image

    def get_item_size(self, item):
        if item == "Chaos Orb" or item == "Divine Orb":
            return {'w': 1, 'h': 1}

        return {'w': self.current_deal.item_info['w'], 'h': self.current_deal.item_info['h']}

    # endregion

    # region Сделка

    def invite_trade(self):
        while not self.find_template('template_trade'):
            if self.trade_invite_number > self.MAX_TRADE_INVITE_NUMBER:
                raise StopStepError(f"Покупатель не принял трейд c {self.MAX_TRADE_INVITE_NUMBER}")

            self.trade_invite_number += 1

            if not self.deal_is_available(self.current_deal):
                raise StopStepError("Не стал кидать трейд, сделка недоступна (покупатель не в ХО)")

            if not self.find_template('template_waiting_trade_request'):
                self.send_to_chat(f"/tradewith {self.current_deal.character_name}")

            time.sleep(2 + self.trade_invite_number)

            if self.stop():
                raise StopStepError("Покупатель не принял трейд")

        self.trade_state = 'not_finished'

    def on_error_trade(self, result):
        if self.trade_state == 'cancelled':
            self.save_current_deal_result(result, 'cancelled')
        elif self.trade_state == 'not_finished':
            self.save_current_deal_result(result, 'ignored_by_seller')

        self.return_deal_items_to_stash()
        self.change_item_qty(self.current_deal.item_name, self.current_deal.item_qty, self.current_deal.position)

    def return_deal_items_to_stash(self):
        self.try_to_open_tab(self.current_deal.item_tab_number,
                             self.current_deal.item_info['tab_type'],
                             self.current_deal.item_info['section'])

        if self.current_deal.item_info['is_layout']:
            self.clear_inventory()
        else:
            cell_pos = self.virtual_inventory.get_last_cell(self.current_deal.item_name)
            inv_region = self.v('region_inventory_fields')
            inv_cell_coords = [int(inv_region[0] + inv_region[2] * (cell_pos[1] + 0.5) / 12),
                               int(inv_region[1] + inv_region[3] * (cell_pos[0] + 0.5) / 5)]
            self.mouse_move_and_click(*inv_cell_coords, duration=.5)
            self.mouse_move_and_click(*self.current_deal.item_coords, duration=.5, sleep_after=.5)
            pyautogui.click(button='right')
            time.sleep(.15 + self.v('button_delay_ms') / 1000)
            keyboard.write(self.current_deal.item_info['note'])
            time.sleep(.15 + self.v('button_delay_ms') / 1000)
            pyautogui.press('enter')
            time.sleep(.15 + self.v('button_delay_ms') / 1000)

    def put_items(self):
        self.from_inventory_to_trade()

    def check_currency(self):
        region = self.v('region_trade_inventory_fields_his')

        divine_qty = 0
        chaos_qty = 0

        while True:

            if not self.find_template('template_trade'):
                raise StopStepError("Трейд закрылся до завершения")

            items_qty = self.count_items(region, accuracy=.5)
            divine_qty = items_qty.get("Divine Orb", 0)
            chaos_qty = items_qty.get("Chaos Orb", 0)

            # Для случаев покупок за дивайны, очень часто будет всё четко, лишние действия не делаем
            if self.current_deal.currency == "divine" \
                    and self.current_deal.divine_qty and divine_qty >= self.current_deal.divine_qty:
                break

            # Для случаев покупок за хаосы, очень часто будет всё четко, лишние действия не делаем
            if self.current_deal.currency == "chaos" \
                    and self.current_deal.chaos_qty and chaos_qty >= self.current_deal.chaos_qty:
                break

            # Остается случай, когда покупатель скинул пасту с одной валютой, а дает другую - считаем по курсу
            if self.enough_currency_qty(divine_qty, chaos_qty):
                break

            if self.stop():
                raise StopStepError(
                    f"Неверное количество валюты для сделки D: {divine_qty} C: {chaos_qty}"
                    f"(нужно D: {self.current_deal.divine_qty} C: {self.current_deal.chaos_qty})")

        self.current_deal.received_currency = {'Divine Orb': divine_qty, 'Chaos Orb': chaos_qty}

    def enough_currency_qty(self, divine_qty, chaos_qty):
        def chaos_qty_from_divine_qty(_divine_qty):
            return round(_divine_qty * (1 / self.chaos_price))

        return (chaos_qty_from_divine_qty(divine_qty) + chaos_qty) >= (chaos_qty_from_divine_qty(
            self.current_deal.divine_qty) + self.current_deal.chaos_qty) * (1 - self.v('price_tolerance') / 100)

    def set_complete_trade(self):
        if self.find_template('template_cancel_complete_trade'):
            # Уже нажата кнопка (т.к. вместо нее появилась кнопка отмены трейда)
            return

        self.click_to('template_complete_trade')

    # endregion

    # region Дождаться завершения трейда

    def wait_confirm(self):
        while True:
            if self.trade_state == 'accepted':
                return
            elif self.trade_state == 'cancelled':
                time.sleep(5)
                raise StopStepError("Трейд отменен продавцом")
            if self.stop():
                raise StopStepError("Не дождался подтверждения от продавца")

            time.sleep(.5)

    def on_complete_trade(self):
        self.say_ty()

        if not self.character_have_another_deal(self.current_deal.character_name):
            self.kick_current_character_from_party()

        self.increase_currency()
        self.notify_to_telegram_for_fill_currency_if_need()

        self.current_deal = DealPOETrade()

    def notify_to_telegram_for_fill_currency_if_need(self):
        currencies_qty = self.db.get_items_qty(["Chaos Orb", "Divine Orb"])
        chaos_qty_notification = self.v('chaos_qty_notification')
        divine_qty_notification = self.v('divine_qty_notification')

        if (chaos_qty_notification and currencies_qty['Chaos Orb'] >= chaos_qty_notification) \
                or (divine_qty_notification and currencies_qty['Divine Orb'] >= divine_qty_notification):

            if int(datetime.now().timestamp()) - self._last_telegram_msg_timestamp > 3600:
                self.send_message_to_telegram(
                    self.msg_for_telegram_with_bot_name(
                        "Продал на достаточное кол-во валюты:\n"
                        f"{currencies_qty.get('Divine Orb', 0)}/{divine_qty_notification} d, "
                        f"{currencies_qty.get('Chaos Orb', 0)}/{chaos_qty_notification} c"
                    )
                )
                self._last_telegram_msg_timestamp = int(datetime.now().timestamp())

    def character_have_another_deal(self, character_name):
        for deal in self.deals:
            if character_name == deal.character_name:
                return True

        return False

    def say_ty(self):
        self.send_to_chat(f"@{self.current_deal.character_name} ty")

    def kick_current_character_from_party(self):
        self.send_to_chat(f"/kick {self.current_deal.character_name}")

    def increase_currency(self):
        for currency, qty in self.current_deal.received_currency.items():
            self.change_item_qty(currency, qty, None)

    # endregion

    def save_current_deal_result(self, result, state):
        pass

    def cancel_any_requests(self):
        template_decline = self.v('template_decline')

        while True:
            if self.need_stop_threads():
                return

            self.check_freeze()

            xywh = self.find_template(template_decline, move_to_1_1=False)

            if xywh:
                with mouse_controller:
                    x, y, w, h = xywh
                    self.mouse_move_and_click(*to_global(template_decline['region'], [x + w * .5, y + h * .5]),
                                              duration=.15, sleep_after=.15)

                time.sleep(.5)

            time.sleep(.5)
