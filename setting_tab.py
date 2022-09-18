from kivy.animation import Animation
from kivy.clock import Clock, mainthread
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty, OptionProperty, \
    ObjectProperty
from kivymd.app import MDApp
from kivymd.uix.behaviors import RoundedRectangularElevationBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.stacklayout import MDStackLayout

import db_requests
import gv

app = MDApp.get_running_app()
Builder.load_file("setting_tab.kv")


class SettingTab(MDStackLayout):

    def __init__(self, **kwargs):
        global app
        app = MDApp.get_running_app()
        super(SettingTab, self).__init__(**kwargs)

    def refresh_settings(self):
        for setting in gv.db.get_settings():
            if setting['type'] == "int":
                self.ids[setting['key']].value = str(setting['value'])
            elif setting['type'] == "list":
                self.ids[setting['key']].value = setting['value'].split(",")
            else:
                self.ids[setting['key']].value = setting['value']

    def save_settings(self):
        errors = [setting_row.text for setting_row in self.ids.values()
                  if isinstance(setting_row, SettingRow) and setting_row.value is None]

        if errors:
            Snackbar(text=f"Не заполнены настройки: {','.join(errors)}").open()
            return

        settings = [(key,
                     ",".join(setting_row.value) if setting_row.type == "list" else setting_row.value,
                     setting_row.type)
                    for key, setting_row in self.ids.items() if isinstance(setting_row, SettingRow)]

        gv.db.save_settings(settings)


class SettingRow(MDBoxLayout):
    value = ObjectProperty(None)
    type = StringProperty("str")

    def set_value(self, value):

        if self.value != value:
            self.value = value
