import os
import time

import pyautogui
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty, ObjectProperty, DictProperty, ListProperty, NumericProperty
from kivymd.app import MDApp
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import OneLineIconListItem
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.stacklayout import MDStackLayout
from kivymd.uix.tab import MDTabs

import bots.common

app = MDApp.get_running_app()
Builder.load_file("setting_tab.kv")


class AppSettingTab(MDStackLayout):

    def __init__(self, **kwargs):
        global app
        app = MDApp.get_running_app()
        super(AppSettingTab, self).__init__(**kwargs)

    def refresh_settings(self):

        for setting in app.db.get_settings(app.bot.key, tuple(self.ids.keys())):
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

        settings = [('any',
                     key,
                     ",".join(setting_row.value) if setting_row.type == "list" else setting_row.value,
                     setting_row.type)
                    for key, setting_row in self.ids.items() if isinstance(setting_row, SettingRow)]

        app.db.save_settings(settings)

    def open_action_variables(self):
        dialog = bots.common.CustomDialog(
            auto_dismiss=False,
            title=f"Настройки параметров бота",
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
    #
    # def update_poe_items(self):
    #     additional_functional.update_poe_items()


class BotSettingTab(MDStackLayout):

    def __init__(self, **kwargs):
        global app
        app = MDApp.get_running_app()
        super(BotSettingTab, self).__init__(**kwargs)

    def refresh_settings(self):

        for setting in app.db.get_settings(app.bot.key, tuple(self.ids.keys())):
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

        settings = [(app.bot.key,
                     key,
                     ",".join(setting_row.value) if setting_row.type == "list" else setting_row.value,
                     setting_row.type)
                    for key, setting_row in self.ids.items() if isinstance(setting_row, SettingRow)]

        app.db.save_settings(settings)

    def open_action_variables(self):
        dialog = bots.common.CustomDialog(
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
    #
    # def update_poe_items(self):
    #     additional_functional.update_poe_items()


class SettingRow(MDBoxLayout):
    dialog_add = ObjectProperty(None)
    dialog_remove = ObjectProperty(None)
    menu = ObjectProperty(None)
    value = ObjectProperty()
    type = StringProperty("str")
    selection = StringProperty("")

    def set_value(self, value):
        if self.value != value:
            self.value = value

    # region Механизм выбора. Работал до реворка, пока закомменчен до необходимости
    # def open_selection(self, caller):
    #     if not self.selection:
    #         Snackbar(text=f"Ошибка кода: Не заполнен параметр выбора selection").open()
    #         return
    #
    #     menu_items = [
    #         {
    #             "viewclass": "SelectionItem",
    #             'icon': "trash-can",
    #             'icon_func': lambda value: self.confirm_remove_item(value),
    #             "text": value,
    #             "text_color": app.theme_cls.primary_color,
    #             "theme_text_color": 'Custom',
    #             "height": dp(56),
    #             "on_release": lambda x=value: self._set_item(x),
    #         } for value in gv.db.get_selection(self.selection)
    #     ]
    #
    #     menu_items.append({
    #         "viewclass": "SelectionItem",
    #         'icon': "plus",
    #         'icon_func': self.open_selection_adder,
    #         "text": "Добавить",
    #         "text_color": app.theme_cls.primary_color,
    #         "theme_text_color": 'Custom',
    #         "height": dp(56),
    #         "on_release": self.open_selection_adder,
    #     })
    #     self.menu = MDDropdownMenu(
    #         caller=caller,
    #         items=menu_items,
    #         position="bottom",
    #         radius=[0, 0, 0, 0],
    #         width_mult=6,
    #         background_color=app.theme_cls.bg_light,
    #     )
    #     self.menu.open()
    #
    # def _set_item(self, new_value):
    #     self.set_value(new_value)
    #     self.menu.dismiss()
    #
    # def open_selection_adder(self, _item=None):
    #     self.dialog_add = MDDialog(
    #         title=f"Добавить значение выбора для {self.text}",
    #         type="custom",
    #         content_cls=MDTextField(),
    #         buttons=[
    #             MDFlatButton(
    #                 text="CANCEL",
    #                 theme_text_color="Custom",
    #                 text_color=app.theme_cls.primary_color,
    #                 on_release=lambda *_: self.dialog_add.dismiss(),
    #             ),
    #             MDFlatButton(
    #                 text="OK",
    #                 theme_text_color="Custom",
    #                 text_color=app.theme_cls.primary_color,
    #                 on_release=lambda *_: self._add_selection(),
    #             ),
    #         ],
    #     )
    #     self.dialog_add.open()
    #
    # def _add_selection(self):
    #     value = self.dialog_add.content_cls.text
    #     gv.db.add_selection_value(self.selection, value)
    #     self.dialog_add.dismiss()
    #     self._set_item(value)
    #
    # def remove_item(self, value):
    #     gv.db.delete_selection_value(self.selection, value)
    #     self.dialog_remove.dismiss()
    #     self.menu.dismiss()
    #
    # def confirm_remove_item(self, value):
    #     self.dialog_remove = MDDialog(
    #         title=f"Удалить элемент: {value}?",
    #         buttons=[
    #             MDFlatButton(
    #                 text="CANCEL",
    #                 theme_text_color="Custom",
    #                 text_color=app.theme_cls.primary_color,
    #                 on_release=lambda *_: self.dialog_remove.dismiss(),
    #             ),
    #             MDFlatButton(
    #                 text="OK",
    #                 theme_text_color="Custom",
    #                 text_color=app.theme_cls.primary_color,
    #                 on_release=lambda *_: self.remove_item(value),
    #             ),
    #         ],
    #     )
    #     self.dialog_remove.open()
    # endregion


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

        self.ids.variables_sections.clear_widgets()

        for section_name, variables in app.bot.variables_setting.items():
            section = VariablesSection(title=section_name, data=variables)
            self.ids.variables_sections.add_widget(section)

    def save_data(self, *args):
        variables = [
                        (app.bot.key,
                         vr.variable.key,
                         vr.variable.get_window_key(),
                         ", ".join(vr.value.split(", ")[:3]) if vr.variable.type in ['template', 'templates']
                         else vr.value
                         )
                        for section in self.ids.variables_sections.children
                        for vr in section.ids.variables.children if vr.value
                    ] + [
                        (app.bot.key,
                         vr.variable.region.key,
                         vr.variable.region.get_window_key(),
                         ", ".join(vr.value.split(", ")[3:])
                         )
                        for section in self.ids.variables_sections.children
                        for vr in section.ids.variables.children if (vr.value
                                                                     and vr.variable.type in ['template', 'templates'])
                    ]

        app.db.save_bots_variable(variables)

    def delete_row(self, row):
        if row.window_resolution == 'relative':
            self.ids.variables_relative.remove_widget(row)
        else:
            self.ids.variables.remove_widget(row)
        Clock.schedule_once(self.dialog_parent.update_height)
    #
    # def add_row(self, instance):
    #     new_variable = VariablesRow(
    #         hint_text=instance.ids.tf.text,
    #         icon_func=self.delete_row,
    #         icon_right_func=
    #         lambda variable_row, exe_name=self.ids.exe_name, delay=self.ids.screenshot_delay:
    #         VariablesRow.get_from_screenshot(variable_row, exe_name, delay),
    #         type=instance.type
    #     )
    #
    #     if self.ids.variables_tabs.get_current_tab() == self.ids.variables_tab:
    #         setting_window_resolution = gv.db.get_settings(app.bot.key, "setting_checkbox_window_resolution")
    #         new_variable.window_resolution = setting_window_resolution[0]['value']
    #         self.ids.variables.add_widget(new_variable)
    #     else:
    #         new_variable.window_resolution = 'relative'
    #         self.ids.variables_relative.add_widget(new_variable)
    #
    #     Clock.schedule_once(self.dialog_parent.update_height)


class VariablesSection(MDBoxLayout):
    title = StringProperty()
    data = ListProperty()

    def __init__(self, **kwargs):
        super(VariablesSection, self).__init__(**kwargs)
        Clock.schedule_once(self.on_data)

    def on_data(self, *args):
        if not self.ids:
            return

        self.ids.variables.clear_widgets()

        for variable in self.data:
            vr = VariablesRow(variable=variable)
            self.ids.variables.add_widget(vr)


class VariablesRow(MDBoxLayout):
    value = StringProperty()
    variable = ObjectProperty()

    icon_right_func = ObjectProperty()
    icons_right = DictProperty()

    # Для функции get_from_screenshot
    click1 = False
    point1 = (0, 0)

    def __init__(self, **kwargs):
        super(VariablesRow, self).__init__(**kwargs)

    def on_variable(self, *args):
        self.value = self.variable.value_for_settings()

    def on_press_textfield_right_icon(self, instance, touch):
        """
        Обработчик нажатия в область иконки текстового поля. Так как иконка - это не объект, а просто текстура
        (картинка), от событие срабатывает, когда: нажатие попало в объект текстового поля, нажатие правее позиции
        картинки. Расчет позиции картинки взял из kivymd/uix/textfield/textfield.kv
        """
        tf = self.ids.tf  # Объект текстового поля
        if not (tf.collide_point(*touch.pos) and tf._icon_right_label):
            # Если клик не попал в объект текстового поля
            return

        icon_pos_x = (tf.x + tf.width - (0 if tf.mode != "round" else dp(4))
                      - tf._icon_right_label.texture_size[0] - dp(8))

        if touch.pos[0] > icon_pos_x:  # Если координаты клика правее начала иконки - считается, что попали:)
            if self.variable:
                try:
                    new_value = self.variable.get_from_screenshot()
                    if new_value:
                        self.value = new_value
                except Exception as e:
                    Snackbar(text=str(e)).open()
            else:
                Snackbar(text="Ошибка разработки бота: Переменная установлена некорректно").open()

    def set_value(self, value):
        self.value = value


class CustomMDTabs(MDTabs):

    def __init__(self, **kwargs):
        super(CustomMDTabs, self).__init__(**kwargs)
        Clock.schedule_once(self.draw_indicator)

    def draw_indicator(self, *args):
        self.tab_indicator_height = self.tab_bar_height

        current_tab_label = self.tab_bar.layout.children[-1]
        self.tab_bar.update_indicator(
            current_tab_label.x, current_tab_label.width
        )
