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

from bots.bot import Bot, Coord, Simple, Template


class PoeTujen(Bot):
    # Обязательные
    icon = 'account-arrow-left'
    name = "ПОЕ: Tujen"
    key = "poe_tujen"

    max_offer = 0

    def __init__(self):
        super(PoeTujen, self).__init__()

        self.set_task_tab_buttons()
        self.set_tasks()
        self.set_variables_setting()
        self.set_windows()

    def set_task_tab_buttons(self):
        self.task_tab_buttons = [
        ]

    def set_tasks(self):
        self.tasks = [
            {
                'name': "Торговаться",
                'timer': 3600,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.reset,
                        'name': "Сбросить начальные данные"
                    },
                    {
                        'func': self.wait_deal,
                        'name': "Ждать сделку"
                    },
                    {
                        'func': self.recognize_max_offer,
                        'name': "Распознать максимальное предложение"
                    },
                    {
                        'func': self.offer_60_percent,
                        'name': "Предложить 60%",
                        'on_error': {'goto': (0, 0)}
                    },
                    {
                        'func': self.offer_70_percent,
                        'name': "Предложить 70%",
                        'on_error': {'goto': (0, 0)}
                    },
                    {
                        'func': self.offer_80_percent,
                        'name': "Предложить 80%",
                        'on_error': {'goto': (0, 0)}
                    },
                    {
                        'func': self.get_deal_any,
                        'name': "Принять любую сделку",
                        'on_error': {'goto': (0, 0)}
                    },
                ]
            },
        ]

    def set_variables_setting(self):
        self.variables_setting = {
            'Окно: Path of Exile': [
                Template(
                    key='template_check_haggle',
                    name=
                    "Шапка с HAGGLE",
                    region=Coord(
                        key='region_check_haggle',
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
                Coord(
                    key='region_offer',
                    name="Область текущего предложения",
                    relative=True,
                    snap_mode='ct',
                    type='region',
                    window='poe_except_inventory'
                ),
                Coord(
                    key='coord_confirm',
                    name="Координаты кнопки CONFIRM",
                    relative=True,
                    snap_mode='ct',
                    type='coord',
                    window='poe_except_inventory'
                ),
            ]
        }

    def set_windows(self):
        self.windows = {
            'main': {'name': ""},
            'poe_except_inventory': {'name': "Path of Exile", 'expression': ('x', 'y', 'w - 0.6166 * h', 'h')}
        }

    def reset(self):
        self.max_offer = 0

    def wait_deal(self):
        self.wait_for_template('template_check_haggle', move_to_1_1=False)

    def recognize_max_offer(self):
        region = self.v('region_offer')

        image = np.array(pyautogui.screenshot(region=region))

        max_offer = image_to_int(image, 30, 'tujen', self.app.s(self.key, 'debug'))
        if max_offer == 0:
            raise ValueError("Не распознал количество")
        else:
            print(max_offer)

        self.max_offer = max_offer

    def offer_60_percent(self):
        self.offer(60, False)

    def offer_70_percent(self):
        self.offer(70)

    def offer_80_percent(self):
        self.offer(80)

    def get_deal_any(self):
        self.offer(100)

    def offer(self, percent, need_check=True):

        if need_check:
            template_settings = self.v('template_check_haggle')
            if not self.find_template(**template_settings):
                raise ValueError("Сделка состоялась или отменена")

        offer_qty = int(math.ceil(self.max_offer * percent / 100))

        self.click_to('region_offer')
        keyboard.send('ctrl+a')
        keyboard.write(str(offer_qty), delay=0)

        self.click_to('coord_confirm')
