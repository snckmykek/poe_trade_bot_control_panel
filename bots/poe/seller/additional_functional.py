import os
import time

import cv2
import numpy as np
import pyautogui
import requests
from kivy.animation import Animation
from kivy.lang import Builder
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty, OptionProperty, \
    ObjectProperty
from kivy.uix.behaviors import ToggleButtonBehavior
from kivy.uix.image import AsyncImage
from kivymd.app import MDApp
from kivymd.uix.behaviors.ripple_behavior import CommonRipple
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRectangleFlatIconButton, MDRectangleFlatButton
from kivymd.uix.list import OneLineIconListItem
from kivymd.uix.snackbar import Snackbar

from bots.common import CustomDialog, text_is_correct

app = MDApp.get_running_app()
Builder.load_file(os.path.abspath(os.path.join(os.path.dirname(__file__), "additional_functional.kv")))


class SellerContent(MDBoxLayout):
    pass


class SellerDealListItem(OneLineIconListItem):
    character_name = StringProperty()
    item_name = StringProperty()
    item_qty = NumericProperty()
    currency = StringProperty()
    chaos_qty = NumericProperty()
    divine_qty = NumericProperty()
    image = StringProperty()



