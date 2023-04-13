import inspect
import math
import os
import re
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
from kivy.properties import DictProperty, ListProperty, NumericProperty, BooleanProperty, StringProperty
from kivymd.uix.button import MDRectangleFlatIconButton
from kivymd.uix.label import MDLabel
from kivymd.uix.snackbar import Snackbar
from win32api import GetSystemMetrics
from kivy.clock import Clock

from bots.bot import Coord, Simple, Template, get_window_param, to_global
from bots.common import CustomDialog, DealPOETrade
from bots.poe.poe_base import PoeBase
from bots.poe.buyer.db_requests import Database
from bots.poe.buyer.additional_functional import Content, Items, Blacklist
from controllers import mouse_controller
from errors import StopStepError


class PoeBuyer(PoeBase):
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
    # TODO Сохранять в настройки (или вообще вынести его в настройки, подумать)
    deal_sort_type: Literal['profit_per_each', 'profit'] = StringProperty('profit_per_each')
    items_left = NumericProperty()
    in_own_hideout = BooleanProperty(False)
    need_update_swag = True
    party_accepted: bool = False
    proxies_queue: list = []
    start_deal_timestamp: int = 0
    stat: dict = DictProperty({'good': 0, 'skipped': 0, 'bad': 0, 'profit': 0})
    swag: dict = DictProperty({'chaos': 0, 'divine': 0, 'current_chaos_coord': [0, 0]})
    trade_thread: threading.Thread = None
    party_thread: threading.Thread = None
    whispers_history: dict = {}
    _last_poe_trade_request: int = 0
    _requests_interval: float = .0

    # region init
    def __init__(self):
        super(PoeBuyer, self).__init__()

        self.set_task_tab_buttons()
        self.set_tasks()
        self.set_windows()

        self.db = Database(os.path.join(self.app.db_path, f"{self.key}.db"))

        Clock.schedule_once(self.delayed_init)

    def set_task_tab_buttons(self):
        self.task_tab_buttons.extend(
            [
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
                    {
                        'func': self.go_home,
                        'name': "ТП в хайдаут"
                    },
                ]
            },
            {
                'name': "Запуск потока ПОЕ трейд и подготовка к торговле",
                'timer': 60,
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
                'name': "Ждать инфу по сделкам",
                'timer': 60,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.wait_trade_info,
                        'on_error': {'goto': (2, 0)},
                        'name': "Ждать информацию по валюте и очередь сделок"
                    },
                ]
            },
            {
                'name': "Назначение сделки",
                'timer': 60,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.prepare_service,
                        'name': "Подготовка служебных данных"
                    },
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
                        # 'on_error': {'goto': (3, 0)},
                        'name': "ТП в хайдаут"
                    },
                    {
                        'func': self.take_currency,
                        'name': "Взять валюту"
                    },
                    {
                        'func': self.wait_party,
                        'on_error': {'func': lambda x: self.save_current_deal_result(x, 'skipped'), 'goto': (3, 1)},
                        'name': "Ждать пати"
                    },
                    {
                        'func': self.teleport,
                        'on_error': {'goto': (3, 3)},
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
                        'on_error': {'func': lambda x: self.save_current_deal_result(x, 'bad'), 'goto': (2, 0)},
                    },
                    {
                        'func': self.put_currency,
                        'name': "Положить валюту",
                        'on_error': {'goto': (4, 0)}
                    },
                    {
                        'func': self.check_items,
                        'name': "Проверить итемы",
                        'on_error': {'goto': (4, 0)}
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
                        'on_error': {'goto': (4, 0)},
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
                    key='button_delay_ms',
                    name="Дополнительная задержка после действий мыши и клавиатуры (ms)",
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
                    name="Координаты ячейки Chaos orb (в т.ч. дополнительных, где могут быть хаосы)",
                    relative=True,
                    snap_mode='lt',
                    type='coord_list',
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
                    name="Статичный кусок экрана, "
                         "однозначно говорящий о загрузке локи (например, сиськи телки где мана)",
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
                    key='region_trade_inventory_fields_his',
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
            'poe_except_inventory': {'name': "Path of Exile", 'expression': ('x', 'y', 'int(w - 0.6166 * h)', 'h')}

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
        Snackbar(
            text="В разработке"
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
                                      not inspect.isfunction(v) and not inspect.ismethod(v) and not inspect.isbuiltin(
                                          v) and k[:2] != '__')

    def stub(self, *_):
        print(f"Заглушка: {self.app.current_task}, {self.app.current_stage}")
        time.sleep(1)

    def on_stage_started_manually(self):
        self.need_update_swag = True

    # region Продажа. Запросы на ПОЕ трейд
    def start_poe_trade(self):
        if not self.trade_thread or not self.trade_thread.is_alive():
            self.trade_thread = threading.Thread(target=lambda *_: self.poetrade_loop(), daemon=True)
            self.trade_thread.start()

    def poetrade_loop(self):

        while not self.currencies_price_is_updated():
            time.sleep(5)

        while True:
            if self.need_stop_threads():
                return

            _start = datetime.now()

            try:
                current_order = self.get_current_order()
                self.update_items_left(current_order)
                self.update_offer_list(current_order)
            except Exception as e:
                self.print_log(f"Ошибка в запросе инфы с трейда.\n" + str(e))

            _interval = self.v('poetrade_info_update_frequency') - (datetime.now() - _start).total_seconds()
            if _interval > 0:
                time.sleep(_interval)

    def currencies_price_is_updated(self):
        try:
            self.update_currency_price()
        except Exception as e:
            self.print_log(f"Ошибка получения валюты: {e}\n")
            return False

        return True

    def update_currency_price(self):

        # Цена дивайна для конвертации дивайна в хаосы
        divine_deals = self.get_deals({'divine': ["chaos", ]})
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
        chaos_deals = self.get_deals({'chaos': ["divine", ]})
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
        items_settings = self.db.get_items()

        order = {'chaos': [
            {
                'item': item_settings['item'],
                'name': item_settings['name'],
                'max_price': item_settings['max_price'],
                'bulk_price': item_settings['bulk_price'],
                'image': item_settings['image'],
                'max_qty': item_settings['max_qty']
            } for item_settings in items_settings
            if (
                    item_settings['use'] and item_settings['max_price']
                    and item_settings['bulk_price'] and item_settings['max_qty']
            )
        ], 'divine': [
            {
                'item': item_settings['item'],
                'name': item_settings['name'],
                'max_price': item_settings['max_price_d'],
                'bulk_price': item_settings['bulk_price_d'],
                'image': item_settings['image'],
                'max_qty': item_settings['max_qty']
            } for item_settings in items_settings
            if (
                    item_settings['use'] and item_settings['max_price_d']
                    and item_settings['bulk_price_d'] and item_settings['max_qty']
            )
        ]}

        return order

    def update_items_left(self, current_order):
        _counted_items = []
        items_left = 0
        for items_i_want in current_order.values():
            for item in items_i_want:
                if item['name'] in _counted_items:
                    continue

                _counted_items.append(item['name'])
                items_left += item['max_qty']

        self.items_left = items_left

    def update_offer_list(self, order):

        self.deals = self.get_deals(order, deal_sort_type=self.deal_sort_type)

        self.print_log("Сделки обновлены")

    def get_deals(self, order, min_stock=1, qty_deals=30,
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
        for item_i_have, items_i_want in order.items():
            for item_i_want in items_i_want:
                simple_item = isinstance(item_i_want, str)

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
                    deal.whisper_template = deal_info['listing']['whisper']

                    deal.price_for_each = deal.currency_min_qty / deal.item_min_qty
                    if not simple_item:
                        deal.profit_per_each = round(item_i_want['bulk_price'] - deal.price_for_each, 3)
                        deal.profit = round(deal.profit_per_each * deal.item_stock, 3)
                        deal.image = item_i_want['image']
                        deal.item_name = item_i_want['name']

                    if simple_item or deal.price_for_each <= item_i_want['max_price']:
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

        self.update_swag_if_necessary()

    def update_swag_if_necessary(self):

        if not self.need_update_swag:
            return

        self.clear_inventory()

        chaos_qty = 0
        divine_qty = 0
        current_chaos_coord = None
        while (not chaos_qty and self.v('min_chaos')) or (not divine_qty and self.v('min_divine')):
            self.try_to_open_currency_tab()

            divine_info = self.get_item_info_by_ctrl_c(['item_name', 'quantity'], self.v('coord_divine'))
            if 'divine' in divine_info.get('item_name', "").lower():
                divine_qty = divine_info.get('quantity', 0)

            chaos_qty = 0
            _min_chaos_qty = 5001
            for chaos_coord in self.v('coord_chaos'):
                chaos_info = self.get_item_info_by_ctrl_c(['item_name', 'quantity'], chaos_coord)
                if 'chaos' in chaos_info.get('item_name', "").lower():
                    _chaos_qty = chaos_info.get('quantity', 0)
                    chaos_qty += _chaos_qty
                    if _chaos_qty < _min_chaos_qty:
                        _min_chaos_qty = _chaos_qty
                        current_chaos_coord = chaos_coord

        if current_chaos_coord is None:
            raise StopStepError("Не смог установить координаты ячейки с хаосами")

        self.swag.update({'chaos': chaos_qty, 'divine': divine_qty, 'current_chaos_coord': current_chaos_coord})
        self.need_update_swag = False

    # endregion

    # region Продажа. Ожидание очереди сделок

    def wait_trade_info(self):
        if not self.deals and not self.in_own_hideout:
            self.go_home()

        while (self.swag['chaos'] == 0 and self.v('min_chaos')) and (self.swag['divine'] == 0 and self.v('min_divine')):
            if self.stop():
                raise StopStepError("Не дождался инфы о валюте в стеше")

        while self.chaos_price == 0 or self.divine_price == 0:
            if self.stop():
                raise StopStepError("Не дождался инфы о цене дивайна")

        while not self.deals:
            if self.stop():
                raise StopStepError("Не дождался инфы о сделках")

    # endregion

    # region Продажа. Подготовка

    def prepare_service(self):
        min_chaos = self.v('min_chaos')
        min_divine = self.v('min_divine')
        if self.swag['chaos'] < min_chaos or self.swag['divine'] < min_divine:
            self.go_home(forced=True)
            raise StopStepError(f"Количество валюты меньше минимальных значений. Chaos: {self.swag['chaos']} "
                                f"(минимум: {min_chaos}), Divine: {self.swag['divine']} (минимум: {min_divine})")

        self.start_deal_timestamp = int(datetime.now().timestamp())

        if not self.party_thread or not self.party_thread.is_alive():
            self.party_thread = threading.Thread(target=lambda *_: self.accept_party(), daemon=True)
            self.party_thread.start()

    # endregion

    # region Продажа. Запрос сделки
    def set_current_deal(self):
        if not self.deals:  # Если нет некст сделки, очищаем поля текущей, чтоб не висело
            self.current_deal = DealPOETrade()

        try:
            current_deal = self.deals.pop(0)
            while self.skip_by_whispers_history(current_deal.character_name):
                current_deal = self.deals.pop(0)
        except IndexError:
            raise StopStepError("Список сделок пуст")

        if current_deal.currency == "chaos":
            available_currency = self.swag['chaos'] + self.swag['divine'] * self.divine_price
        else:
            available_currency = self.swag['divine'] + self.swag['chaos'] * self.chaos_price

        items_settings = self.db.get_items(current_deal.item)
        qty_left = items_settings[0]['max_qty'] if items_settings else 0

        if qty_left == 0:
            self.remove_deals_with_item(current_deal.item)
            raise StopStepError(f"Товар {current_deal.item} полностью закуплен")

        item_amount = 0
        currency_amount = 0
        while item_amount + current_deal.item_min_qty <= qty_left \
                and item_amount + current_deal.item_min_qty <= current_deal.item_stock \
                and currency_amount + current_deal.currency_min_qty <= available_currency:
            item_amount += current_deal.item_min_qty
            currency_amount += current_deal.currency_min_qty

        if item_amount == 0:
            raise StopStepError(f"Количество для покупки: 0. ID сделки: {current_deal.id}")

        if current_deal.currency == "chaos":
            current_deal.divine_qty = currency_amount // self.divine_price
            current_deal.chaos_qty = currency_amount % self.divine_price
        else:
            frac_divine, int_divine = math.modf(currency_amount)
            current_deal.divine_qty = int(int_divine)
            current_deal.chaos_qty = round(frac_divine / self.chaos_price)

        if self.swag['chaos'] < current_deal.chaos_qty or self.swag['divine'] < current_deal.divine_qty:
            raise StopStepError(f"Недостаточно валюты. Нужно/всего: "
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

        current_deal.whisper = current_deal.whisper_template.format(
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
        self.open_stash()

        # Пока выкладываем каждый раз тупа всё из инвентаря и скрином проверяем, что всё ок
        self.clear_inventory()
        self.try_to_open_currency_tab()
        self.update_swag_if_necessary()

        self.from_stash_to_inventory(self.current_deal.divine_qty, 'divine', 10, self.swag['divine'])
        self.from_stash_to_inventory(self.current_deal.chaos_qty, 'chaos', 20, self.swag['chaos'])

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
                raise StopStepError(f"Не удалось выложить валюту из инвентаря с {attempts} попыток")

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

    def try_to_open_currency_tab(self):
        self.open_stash()
        self.mouse_move_and_click(*self.v('coord_currency_tab'))
        time.sleep(1)

    def get_item_coord(self, item):
        if item == 'divine':
            item_coord = self.v('coord_divine')
        elif item == 'chaos':
            item_coord = self.swag['current_chaos_coord']
        else:
            raise StopStepError(f"Неверно указан предмет: '{item}'")

        return item_coord

    # Пока не используется, тупа clear_inventory
    def empty_cell_with_remainder(self, inv_region, item, stack_size):
        last_cell_coord = self.virtual_inventory.get_last_cell(item)
        last_cell_qty = self.virtual_inventory.get_qty(last_cell_coord)

        if last_cell_qty == stack_size:  # Полная ячейка
            return

        with mouse_controller:
            self.mouse_move(int(inv_region[0] + inv_region[2] * (last_cell_coord[1] + 0.5) / 12),
                            int(inv_region[1] + inv_region[3] * (last_cell_coord[0] + 0.5) / 5),
                            .2)
            self.key_down('ctrl')
            self.mouse_click()
            self.key_up('ctrl')

        self.virtual_inventory.empty_cell(*last_cell_coord)

    def put_remainder(self, inv_region, item, qty, item_size=None):

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
                raise StopStepError("Не смог выложить нецелую часть валюты")

            self.check_freeze()

            with mouse_controller:

                if attempt:
                    time.sleep(.2)
                    self.key_down('ctrl', sleep_after=.1)
                    self.mouse_click(*cell_coords, clicks=2, interval=.015, sleep_after=.1)
                    self.key_up('ctrl', sleep_after=.15)

                if qty >= item_qty_left_in_cell:
                    self.mouse_move(*item_coord, duration=.1, sleep_after=.15)
                    self.key_down('Ctrl', sleep_after=.15)
                    self.mouse_click(sleep_after=.15)
                    self.key_up('Ctrl', sleep_after=.15)

                    self.need_update_swag = True
                    self.update_swag_if_necessary()
                    self.need_update_swag = True  # На некст заходе еще раз проверить всё

                    _additional_qty = qty - item_qty_left_in_cell
                    if _additional_qty:
                        item_coord, item_qty_left_in_cell = self.get_item_coord_and_qty(item)

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

            _, counted = self.get_item_and_qty_in_cell(cell_coords)

            attempt += 1

        self.virtual_inventory.put_item(item, qty, first_empty_cell)

        with mouse_controller:
            self.mouse_move(1, 1)

    def change_whole_part_in_inventory(self, inv_region, currency_coord, item, stack_size, whole_part_qty):
        cells_with_item = self.virtual_inventory.get_sorted_cells(item)
        current_whole_part_qty = len(cells_with_item)

        delta = whole_part_qty - current_whole_part_qty

        while delta != 0:
            if delta > 0:  # Нужно доложить в инвентарь из стеша
                for cell_coord in self.virtual_inventory.get_sorted_cells('empty'):
                    with mouse_controller:
                        self.mouse_move(*currency_coord, .2)
                        self.key_down('ctrl')
                        self.mouse_click()
                        self.key_up('ctrl')

                    self.virtual_inventory.put_item(item, stack_size, cell_coord)

                    delta = len(set([]) & set([]))

                    if delta == 0:
                        break

            elif delta < 0:  # Нужно убрать из инвентаря
                cells_for_empty = list(reversed(cells_with_item))[-1 * delta]
                self.items_from_cells(inv_region, cells_for_empty)

            if self.stop():
                raise StopStepError("Не смог выложить валюту из стеша")

    # Временно вместо недописанной change_whole_part_in_inventory
    def put_whole_part_in_inventory(self, inv_region, item, stack_size, whole_part_qty, item_size=None):

        if whole_part_qty == 0:
            return

        item_coord, item_qty_left_in_cell = self.get_item_coord_and_qty(item)

        additional_delay = .3 if item_qty_left_in_cell <= whole_part_qty * stack_size else 0
        cell_number = 0

        cells_with_items_from_screen = []

        attempt = 0
        counted = 0
        while counted != whole_part_qty:
            if self.stop() or attempt >= 5:
                raise StopStepError(f"Не смог взять валюту из стеша с {attempt} попыток")

            self.check_freeze()

            with mouse_controller:
                self.mouse_move(*item_coord)

            self.key_down('ctrl')
            need_more = whole_part_qty - counted
            for i in range(need_more):  # Нужно доложить в инвентарь из стеша
                with mouse_controller:
                    self.mouse_click(*item_coord, sleep_after=.035 + additional_delay)

                item_qty_left_in_cell -= stack_size
                if item_qty_left_in_cell <= 0:
                    self.key_up('ctrl')

                    self.need_update_swag = True
                    self.update_swag_if_necessary()
                    self.need_update_swag = True  # На некст заходе еще раз проверить всё

                    _additional_qty = -item_qty_left_in_cell
                    if _additional_qty:
                        item_coord, item_qty_left_in_cell = self.get_item_coord_and_qty(item)

                        with mouse_controller:
                            self.key_down('Shift', sleep_after=.35)
                            self.mouse_move_and_click(*item_coord, sleep_after=.35)
                            self.key_up('Shift', sleep_after=.35)
                            pyautogui.write(f'{_additional_qty}')
                            time.sleep(.15)
                            pyautogui.press('Enter')
                            time.sleep(.15)
                            self.mouse_move(
                                *self.cell_coords_by_position(inv_region, cell_number // 5, cell_number % 5),
                                sleep_after=.35
                            )
                            self.mouse_click(sleep_after=.35)

                    self.key_down('ctrl')

                cell_number += 1

            self.key_up('ctrl')

            cells_with_items_from_screen = self.get_cells_with_item(inv_region, item=item, need_clear_region=True)
            counted = len(cells_with_items_from_screen)

            attempt += 1

        # Записываем в вирт инвент
        for cell_pos in cells_with_items_from_screen:
            self.virtual_inventory.put_item(item, stack_size, cell_pos)

        with mouse_controller:
            self.mouse_move(1, 1)

    def get_item_coord_and_qty(self, item):
        item_coord = self.get_item_coord(item)

        _, item_qty_in_cell = self.get_item_and_qty_in_cell(item_coord)
        while not item_qty_in_cell:
            self.try_to_open_currency_tab()
            _, item_qty_in_cell = self.get_item_and_qty_in_cell(item_coord)

            if self.stop():
                raise StopStepError("Не смог открыть валютную вкладку")

        return item_coord, item_qty_in_cell

    def close_x_tabs(self):
        self.click_to('template_x_button', wait_template=False)
        time.sleep(1)

    @staticmethod
    def cell_coords_by_position(inv_region, col, row):
        return [int(inv_region[0] + inv_region[2] * (col + 0.5) / 12),
                int(inv_region[1] + inv_region[3] * (row + 0.5) / 5)]

    def wait_party(self):
        timeout = self.v('party_timeout')
        _start = datetime.now()

        while not self.party_accepted:
            if self.check_chat_need_skip():
                raise StopStepError("Пропускаем по стоп-слову из чата")

            if self.add_changed_deal_and_skip_current():
                raise StopStepError("Сделка была изменена и добавлена заново в список сделок. Эту прерываем")

            if self.stop() or (timeout and (datetime.now() - _start).total_seconds() > timeout):
                raise StopStepError("Не дождался пати")
            else:
                time.sleep(.5)

    def accept_party(self):

        template_accept = self.v('template_accept')

        while True:
            if self.need_stop_threads():
                return

            if not self.party_accepted:
                self.check_freeze()

                xywh = self.find_template(template_accept, move_to_1_1=False)

                if xywh:
                    with mouse_controller:
                        x, y, w, h = xywh
                        self.mouse_move_and_click(*to_global(template_accept['region'], [x + w * .5, y + h * .5]))

                    time.sleep(.5)

                    if not self.find_template(template_accept, move_to_1_1=False):
                        self.party_accepted = True

            time.sleep(.5)

    def add_changed_deal_and_skip_current(self):
        # TODO: не учитывать ник, очищать во всем оте client.txt после прочтения
        # Если продавец пишет "3 left", "have 3", то добавляем в список на 1 место новую сделку, эту скипаем
        # new_deal_qty = math.floor(
        #     self.new_deal_qty() / self.current_deal.item_min_qty) * self.current_deal.item_min_qty
        #
        # if new_deal_qty:
        #     self.current_deal.item_stock = new_deal_qty
        #     self.current_deal.profit = self.current_deal.profit_per_each * new_deal_qty
        #
        #     self.deals.insert(0, self.current_deal)
        #     self.whispers_history.pop(self.current_deal.character_name)
        #     self.clear_logs()
        #
        #     return True

        return False

    def new_deal_qty(self):

        line_with_new_qty = self._get_line_with_new_qty()

        number_in_line = re.findall(r'\d+', line_with_new_qty)
        if len(number_in_line) == 1:
            return int(number_in_line[0])
        else:
            return 0

    def _get_line_with_new_qty(self):
        new_qty_words = ['left', 'only', 'have']

        with open(self.v('logs_path'), 'r', encoding="utf-8") as f:
            for line in f:
                if self.current_deal.character_name in line:
                    for word in new_qty_words:
                        if word in line.lower():
                            print(f"Найдено слово '{word}' в строке '{line}'")
                            try:
                                return line.split('@From')[1]
                            except IndexError:
                                pass

        return ""

    def teleport(self):
        self.send_to_chat(f"/hideout {self.current_deal.character_name}")
        time.sleep(self.v('waiting_for_teleport'))
        self.wait_for_template('template_game_loaded')  # Ждем загрузку

        # Если мы не можем сделать ТП, то мы в пати с кем-то другим. Проверяем этот вариант
        if self.check_cannot_teleport():
            self.leave_party()
            self.clear_logs()
            self.party_accepted = False
            raise StopStepError(f"Не смог сделать ТП, игрок {self.current_deal.character_name} не в пати")

        self.in_own_hideout = False

    def check_cannot_teleport(self):
        with open(self.v('logs_path'), 'r', encoding="utf-8") as f:
            for line in f:
                if 'You cannot currently access' in line:
                    return True

        return False

    def get_item_size(self, item):
        if item == 'Prime Chaotic Resonator':
            return {'w': 2, 'h': 2}
        #
        # if 'chaos' in item.lower() or 'divine' in item.lower():
        #     return {'w': 1, 'h': 1}

        return {'w': 1, 'h': 1}

    # endregion

    # region Продажа. Сделка
    def wait_trade(self):
        timeout = self.v('trade_timeout')

        _start = datetime.now()

        while True:
            time.sleep(.5)

            if self.find_template('template_trade'):
                break

            self.click_to('template_accept', wait_template=False)

            if self.stop() or (timeout and (datetime.now() - _start).total_seconds() > timeout):
                self.leave_party()
                raise StopStepError("Не дождался трейда")

        self.clear_logs()

    def put_currency(self):
        self.from_inventory_to_trade()

    def check_items(self):
        qty = 0
        region = self.v('region_trade_inventory_fields_his')
        while qty < self.current_deal.item_qty:

            if not self.find_template('template_trade'):
                raise StopStepError("Трейд закрылся до завершения")

            qty = self.count_items(region, accuracy=.5).get(self.current_deal.item_name, 0)

            if self.stop():
                raise StopStepError(
                    f"Неверное количество предметов для сделки {qty} (нужно {self.current_deal.item_qty})")

    def set_complete_trade(self):
        if self.find_template('template_cancel_complete_trade'):
            # Уже нажата кнопка (т.к. вместо нее появилась кнопка отмены трейда)
            return

        self.click_to('template_complete_trade')

    # endregion

    # region После трейда

    def wait_confirm(self):
        while True:
            trade_status = self.get_trade_status()

            if trade_status == 'accepted':
                return
            elif trade_status == 'cancelled':
                raise StopStepError("Трейд отменен продавцом")

            if self.stop():
                raise StopStepError("Не дождался подтверждения от продавца")

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

    def get_item_image(self, item):
        return self.db.get_poe_item_image(item)

    # region Общие функции
    def go_home(self, forced=False):
        if self.in_own_hideout and not forced:
            return

        while True:
            self.wait_for_template('template_game_loaded')
            self.send_to_chat("/hideout")
            time.sleep(self.v('waiting_for_teleport'))

            if self.find_template('template_stash'):
                self.in_own_hideout = True
                break

    def save_current_deal_result(self, result, state):
        self.db.save_deal_history([
            self.start_deal_timestamp,  # date
            self.current_deal.id,  # id
            self.current_deal.character_name,
            bool(state == 'completed'),  # completed
            result['error'],  # error
            self.current_deal.item,
            self.current_deal.item_qty,
            self.current_deal.price_for_each,
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
