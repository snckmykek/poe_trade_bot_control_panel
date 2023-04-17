import os
import time

import cv2
import numpy as np
import pyautogui
import requests
from kivy.animation import Animation
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty, OptionProperty, \
    ObjectProperty
from kivy.uix.behaviors import ToggleButtonBehavior
from kivy.uix.image import AsyncImage
from kivymd.app import MDApp
from kivymd.uix.behaviors.ripple_behavior import CommonRipple
from kivymd.uix.behaviors.toggle_behavior import MDToggleButton
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRectangleFlatIconButton, MDRectangleFlatButton, MDFlatButton
from kivymd.uix.list import OneLineIconListItem
from kivymd.uix.menu import MDDropdownMenu
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


class TabsManager(MDBoxLayout):
    title = "Менеджер вкладок"
    dialog_parent = ObjectProperty()
    buttons = []
    layouts = {}

    def __init__(self, **kwargs):
        super(TabsManager, self).__init__(**kwargs)

        global app
        app = MDApp.get_running_app()

        self.buttons = [
            {
                'text': "Добавить строку",
                'icon': 'plus',
                'on_release': self.add_row
            },
            {
                'text': "Отменить",
                'icon': 'window-close',
                'on_release': self.cancel
            },
            {
                'text': "Обновить",
                'icon': 'refresh',
                'on_release': self.refresh
            },
            {
                'text': "Сохранить",
                'icon': 'check',
                'on_release': self.save
            },
        ]

        self.layouts_menu = MDDropdownMenu(width_mult=4)

    def on_pre_open(self, *args):
        bot = MDApp.get_running_app().bot
        self.layouts = bot.db.get_tabs_layouts()
        self.layouts_menu.items = [
            {
                'text': layout,
                'viewclass': "OneLineListItem",
                'on_release': lambda x=layout: self.layout_menu_callback(x),
            } for layout in self.layouts.keys()
        ]

        self.refresh()

    def cancel(self, *args):
        self.dialog_parent.dismiss()

    def save(self, *args):

        bot = MDApp.get_running_app().bot

        tabs = []

        for tab_row in self.ids.tabs_box.children:
            layout = tab_row.ids.tab_layout.ids.label_item.text

            sections_names = [section_button.text for section_button in tab_row.ids.tab_sections.children
                              if section_button.state == 'down']
            if sections_names:
                sections = ','.join(sections_names)
            elif self.layouts[layout]:
                sections = 'skip'
            else:
                sections = ''

            tabs.append(
                [
                    tab_row.ids.tab_number.text if tab_row.ids.tab_number.text else tab_row.ids.tab_number.hint_text,
                    tab_row.ids.use.active,
                    tab_row.ids.tab_name.text if tab_row.ids.tab_name.text else tab_row.ids.tab_name.hint_text,
                    layout,
                    sections
                ]
            )

        bot.db.save_tabs_info(tabs)
        self.dialog_parent.dismiss()

    def refresh(self, *args):
        self.ids.tabs_box.clear_widgets()

        bot = MDApp.get_running_app().bot
        for tab_info in sorted(bot.db.get_tabs_info(), key=lambda tab: int(tab['tab_number'])):
            tr = TabRow(
                tab_number=tab_info['tab_number'],
                tab_name=tab_info['tab_name'],
                tab_layout=tab_info['tab_layout'],
                use=tab_info['use'],
                remove_tab=self.delete_row,
                open_layouts_menu=self.open_layouts_menu,
                change_sections_from_layout=self.change_sections_from_layout
            )

            section_box = tr.ids.tab_sections
            section_box.clear_widgets()
            for section in self.layouts[tab_info['tab_layout']]:
                section_active = section in tab_info['sections'].split(",")
                section_box.add_widget(
                    MyToggleButton(
                        text=section, state='down' if section_active else 'normal',
                        md_bg_color=[1, 1, 1, .3 if section_active else 0]
                    )
                )

            self.ids.tabs_box.add_widget(tr)

    def set_use_all_tabs(self, value):
        for item in self.ids.tabs_box.children:
            item.use = value

    def delete_row(self, row):
        self.ids.tabs_box.remove_widget(row)

    def open_layouts_menu(self, caller):
        self.layouts_menu.caller = caller
        self.layouts_menu.open()

    def layout_menu_callback(self, new_layout):
        self.layouts_menu.caller.set_item(new_layout)
        self.layouts_menu.dismiss()

    def change_sections_from_layout(self, section_box, new_layout):
        section_box.clear_widgets()
        for section in self.layouts[new_layout]:
            section_active = False
            section_box.add_widget(
                MyToggleButton(
                    text=section, state='down' if section_active else 'normal',
                    md_bg_color=[1, 1, 1, .3 if section_active else 0]
                )
            )

    def add_row(self, *args):
        max_tab_number = -1
        for tab_row in self.ids.tabs_box.children:
            tab_number = int(float(tab_row.ids.tab_number.text if tab_row.ids.tab_number.text
                                   else tab_row.ids.tab_number.hint_text))
            if tab_number > max_tab_number:
                max_tab_number = tab_number

        tr = TabRow(
            tab_number=str(max_tab_number + 1),
            tab_name="",
            tab_layout="common",
            use=True,
            remove_tab=self.delete_row,
            open_layouts_menu=self.open_layouts_menu,
            change_sections_from_layout=self.change_sections_from_layout
        )

        self.ids.tabs_box.add_widget(tr)


class MyToggleButton(MDFlatButton, MDToggleButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.background_down = [1, 1, 1, .3]
        self.background_normal = [1, 1, 1, 0]


class TabRow(MDBoxLayout):
    tab_number = StringProperty()
    tab_name = StringProperty()
    tab_layout = StringProperty()
    use = BooleanProperty(False)

    remove_tab = ObjectProperty()
    open_layouts_menu = ObjectProperty()
    change_sections_from_layout = ObjectProperty()

    def __init__(self, **kwargs):
        super(TabRow, self).__init__(**kwargs)
