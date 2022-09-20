import os
import time

import pyautogui
from kivy.animation import Animation
from kivy.clock import Clock, mainthread
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty, OptionProperty, \
    ObjectProperty, DictProperty
from kivymd.app import MDApp
from kivymd.uix.behaviors import RoundedRectangularElevationBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton
from kivymd.uix.card import MDCard, MDCardSwipe
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.list import OneLineListItem, OneLineAvatarIconListItem, OneLineIconListItem
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.stacklayout import MDStackLayout
from kivymd.uix.textfield import MDTextField

import cv2
import numpy as np
import pywintypes
import win32gui
from pygetwindow import Window

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

        for setting in gv.db.get_settings(app.type, tuple(self.ids.keys())):
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

        settings = [(app.type,
                     key,
                     ",".join(setting_row.value) if setting_row.type == "list" else setting_row.value,
                     setting_row.type)
                    for key, setting_row in self.ids.items() if isinstance(setting_row, SettingRow)]

        gv.db.save_settings(settings)
        app.update_action_variables()

    def open_action_variables(self):
        dialog = MDDialog(
            auto_dismiss=False,
            title=f"Настройки шаблонов и координат",
            type="custom",
            content_cls=VariablesBox(),
            buttons=[
                MDFlatButton(
                    text="CANCEL",
                    theme_text_color="Custom",
                    text_color=app.theme_cls.primary_color,
                ),
                MDFlatButton(
                    text="OK",
                    theme_text_color="Custom",
                    text_color=app.theme_cls.primary_color,
                ),
            ],
        )
        dialog.content_cls.dialog_parent = dialog
        dialog.buttons[0].bind(on_release=dialog.dismiss)
        dialog.buttons[1].bind(on_release=dialog.content_cls.save_data)
        dialog.buttons[1].bind(on_release=dialog.dismiss)
        dialog.open()


class SettingRow(MDBoxLayout):
    dialog_add = ObjectProperty(None)
    dialog_remove = ObjectProperty(None)
    menu = ObjectProperty(None)
    value = ObjectProperty(None)
    type = StringProperty("str")
    selection = StringProperty("")

    def set_value(self, value):
        if self.value != value:
            self.value = value

    def open_selection(self, caller):
        if not self.selection:
            Snackbar(text=f"Ошибка кода: Не заполнен параметр выбора selection").open()
            return

        menu_items = [
            {
                "viewclass": "SelectionItem",
                'icon': "trash-can",
                'icon_func': lambda value: self.confirm_remove_item(value),
                "text": value,
                "text_color": app.theme_cls.primary_color,
                "theme_text_color": 'Custom',
                "height": dp(56),
                "on_release": lambda x=value: self._set_item(x),
            } for value in gv.db.get_selection(self.selection)
        ]

        menu_items.append({
            "viewclass": "SelectionItem",
            'icon': "plus",
            'icon_func': self.open_selection_adder,
            "text": "Добавить",
            "text_color": app.theme_cls.primary_color,
            "theme_text_color": 'Custom',
            "height": dp(56),
            "on_release": self.open_selection_adder,
        })
        self.menu = MDDropdownMenu(
            caller=caller,
            items=menu_items,
            position="bottom",
            radius=[0, 0, 0, 0],
            width_mult=6,
            background_color=app.theme_cls.bg_light,
        )
        self.menu.open()

    def _set_item(self, new_value):
        self.set_value(new_value)
        self.menu.dismiss()

    def open_selection_adder(self, _item=None):
        self.dialog_add = MDDialog(
            title=f"Добавить значение выбора для {self.text}",
            type="custom",
            content_cls=MDTextField(),
            buttons=[
                MDFlatButton(
                    text="CANCEL",
                    theme_text_color="Custom",
                    text_color=app.theme_cls.primary_color,
                    on_release=lambda *_: self.dialog_add.dismiss(),
                ),
                MDFlatButton(
                    text="OK",
                    theme_text_color="Custom",
                    text_color=app.theme_cls.primary_color,
                    on_release=lambda *_: self._add_selection(),
                ),
            ],
        )
        self.dialog_add.open()

    def _add_selection(self):
        value = self.dialog_add.content_cls.text
        gv.db.add_selection_value(self.selection, value)
        self.dialog_add.dismiss()
        self._set_item(value)

    def remove_item(self, value):
        gv.db.delete_selection_value(self.selection, value)
        self.dialog_remove.dismiss()
        self.menu.dismiss()

    def confirm_remove_item(self, value):
        self.dialog_remove = MDDialog(
            title=f"Удалить элемент: {value}?",
            buttons=[
                MDFlatButton(
                    text="CANCEL",
                    theme_text_color="Custom",
                    text_color=app.theme_cls.primary_color,
                    on_release=lambda *_: self.dialog_remove.dismiss(),
                ),
                MDFlatButton(
                    text="OK",
                    theme_text_color="Custom",
                    text_color=app.theme_cls.primary_color,
                    on_release=lambda *_: self.remove_item(value),
                ),
            ],
        )
        self.dialog_remove.open()


class SelectionItem(OneLineIconListItem):
    icon_func = ObjectProperty()
    icon = StringProperty()
    text = StringProperty()


class VariablesBox(MDBoxLayout):
    dialog_parent = ObjectProperty()

    def __init__(self, **kwargs):
        super(VariablesBox, self).__init__(**kwargs)
        self.update_data()

    def update_data(self, *args):
        setting = gv.db.get_settings(app.type, "exe_name")
        if setting:
            self.ids.exe_name.text = setting[0]['value']

        setting = gv.db.get_settings(app.type, "screenshot_delay")
        if setting:
            self.ids.screenshot_delay.text = setting[0]['value']

        self.ids.variables.clear_widgets()

        for variable in gv.db.get_action_variables(app.type):
            self.ids.variables.add_widget(
                VariablesRow(
                    hint_text=variable['key'],
                    icon_func=self.delete_row,
                    icon_right_func=
                    lambda variables_row, exe_name=self.ids.exe_name, delay=self.ids.screenshot_delay:
                    VariablesRow.get_from_screenshot(variables_row, exe_name, delay),
                    text=variable['value'],
                    type=variable['type']
                )
            )

        self.ids.variables.add_widget(
            VariablesRow(
                hint_text="Добавить",
                icon="plus",
                icon_func=self.add_row,
                icons_right={
                    'region': 'vector-square-plus',
                    'coord': 'vector-point-plus',
                    'template': 'image-plus-outline',
                    'text': 'credit-card-plus-outline'
                },
                icon_right_func=VariablesRow.change_type,
                type='region'
            )
        )

    def save_data(self, *args):
        setting_window_resolution = gv.db.get_settings(app.type, "setting_checkbox_window_resolution")
        variables = [(app.type,
                      setting_window_resolution[0]['value'],
                      variable.hint_text,
                      variable.text,
                      variable.type)
                     for variable in self.ids.variables.children if variable.hint_text != "Добавить"]

        gv.db.save_action_variables(variables)

        settings = [
            (app.type, 'exe_name', self.ids.exe_name.text, 'str'),
            (app.type, 'screenshot_delay', self.ids.screenshot_delay.text, 'str'),
        ]

        gv.db.save_settings(settings)
        app.update_action_variables()

    def delete_row(self, row):
        self.ids.variables.remove_widget(row)
        Clock.schedule_once(self.dialog_parent.update_height)

    def add_row(self, instance):
        self.ids.variables.add_widget(
            VariablesRow(
                hint_text=instance.ids.tf.text,
                icon_func=self.delete_row,
                icon_right_func=
                lambda variable_row, exe_name=self.ids.exe_name, delay=self.ids.screenshot_delay:
                VariablesRow.get_from_screenshot(variable_row, exe_name, delay),
                type=instance.type
            ),
            1
        )

        Clock.schedule_once(self.dialog_parent.update_height)


class VariablesRow(MDBoxLayout):
    text = StringProperty()
    hint_text = StringProperty()
    icon = StringProperty()
    icon_func = ObjectProperty()
    icons_right = DictProperty()
    icon_right_func = ObjectProperty()
    type = StringProperty()

    # Для функции get_from_screenshot
    click1 = False
    point1 = (0, 0)

    def __init__(self, **kwargs):
        super(VariablesRow, self).__init__(**kwargs)
        self.ids.tf.bind(on_touch_down=self.on_press_textfield_right_icon)

    def on_press_textfield_right_icon(self, instance, touch):
        """
        Обработчик нажатия в область иконки текстового поля. Так как иконка - это не объект, а просто текстура
        (картинка), от событие срабатывает, когда: нажатие попало в объект текстового поля, нажатие правее позиции
        картинки. Расчет позиции картинки взял из kivymd/uix/textfield/textfield.kv
        """
        tf = self.ids.tf  # Объект текстового поля
        if not (self.icons_right and self.type and tf.collide_point(*touch.pos)):  # Входит ли клик в объект
            return

        icon_pos_x = (tf.x + tf.width - (0 if tf.mode != "round" else dp(4))
                      - tf._icon_right_label.texture_size[0] - dp(8))

        if touch.pos[0] > icon_pos_x:  # Если координаты клика правее начала иконки - считается, что попали:)
            if self.icon_right_func:
                self.icon_right_func(self)
            else:
                Snackbar(text="Функция для кнопки не задана").open()

    def set_value(self, value):
        self.text = value

    def change_type(self):
        keys = list(self.icons_right.keys())
        try:
            self.type = keys[keys.index(self.type) + 1]
        except IndexError:
            self.type = keys[0]

    def get_from_screenshot(self, exe_name, delay):
        if self.type == 'text':
            Snackbar(text=f"Тип переменной: {self.type}. Возможен только ручной ввод").open()
            return

        if exe_name.text:
            hwnd = win32gui.FindWindow(None, exe_name.text)
            try:
                rect = win32gui.GetWindowRect(hwnd)
            except pywintypes.error:
                Snackbar(text=f"Неверно указано название окна приложения или оно не запущено: {exe_name.text}").open()
                return
        else:
            from win32api import GetSystemMetrics
            rect = [0, 0, GetSystemMetrics(0), GetSystemMetrics(1)]

        x = rect[0]
        y = rect[1]
        w = rect[2] - x
        h = rect[3] - y

        time.sleep(int(delay.text))

        img_rgb = pyautogui.screenshot(region=[x, y, w, h])
        img = cv2.cvtColor(np.array(img_rgb), 2)
        self.click1 = False
        self.point1 = (0, 0)

        def click(event, click_x, click_y, flags, params):
            if event == cv2.EVENT_LBUTTONDOWN:
                self.click1 = True
                self.point1 = (click_x, click_y)
            elif event == cv2.EVENT_MOUSEMOVE and self.click1:
                if self.type != 'coord':
                    img_copy = img.copy()
                    cv2.rectangle(img_copy, self.point1, (click_x, click_y), (0, 0, 255), 2)
                    cv2.imshow("Image", img_copy)
            elif event == cv2.EVENT_LBUTTONUP:
                self.click1 = False
                if self.type == 'coord':
                    img_copy = img.copy()
                    cv2.line(img_copy, (click_x - 20, click_y), (click_x - 5, click_y), (0, 0, 255), 2)
                    cv2.line(img_copy, (click_x, click_y - 20), (click_x, click_y - 5), (0, 0, 255), 2)
                    cv2.line(img_copy, (click_x + 20, click_y), (click_x + 5, click_y), (0, 0, 255), 2)
                    cv2.line(img_copy, (click_x, click_y + 20), (click_x, click_y + 5), (0, 0, 255), 2)
                    cv2.imshow("Image", img_copy)
                # sub_img = img[self.point1[1]:click_y, self.point1[0]:click_x]
                # cv2.imshow("subimg", sub_img)

                if self.type == 'coord':
                    new_value = ", ".join(map(str, [click_x, click_y]))
                elif self.type == 'region':
                    new_value = ", ".join(map(str, [*self.point1, click_x, click_y]))
                elif self.type == 'template':
                    setting = gv.db.get_settings(app.type, "setting_checkbox_window_resolution")
                    if setting:
                        directory = setting[0]['value']
                    else:
                        directory = "common"
                    templates_path = os.path.join(r"images\templates", directory)

                    if not os.path.exists(templates_path):
                        os.mkdir(templates_path)

                    template_name = f"{self.hint_text}.png"

                    cv2.imwrite(os.path.join(templates_path, template_name),
                                img[self.point1[1]:click_y, self.point1[0]:click_x])
                    new_value = template_name
                else:
                    Snackbar(text="Ошибка кода: Тип настройки не указан").open()
                    new_value = ""

                self.text = new_value

        cv2.namedWindow("Image")
        cv2.setMouseCallback("Image", click)
        cv2.imshow("Image", img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
