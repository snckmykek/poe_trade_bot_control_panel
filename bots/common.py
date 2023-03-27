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
from kivymd.uix.behaviors import CommonElevationBehavior
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.textfield import MDTextField
from common import resource_path

Builder.load_file(resource_path('bots\\common.kv'))


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
    item_stock = 0
    item_min_qty = 0
    item_stack_size = 0
    item_tab_number = 0
    item_coords = [0, 0]
    image = ""

    c_price = 0
    profit_per_each = 0
    profit = 0
    whisper = ""

    received_currency: dict = None
    added_timestamp: int = 0

    item_info: dict = None
    position: dict = None

    def get(self, attr, default=None):
        return getattr(self, attr, super(DealPOETrade, self).get(attr, default))

    def items(self):
        _items = super(DealPOETrade, self).items()

        return list(_items) + list(self.__dict__.items())

    def get_value(self, key):
        return self.__dict__.get(key, "")


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


class CustomMDCard(MDCard, CommonElevationBehavior):
    pass


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
