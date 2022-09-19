from kivy.animation import Animation
from kivy.clock import Clock, mainthread
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty, OptionProperty, \
    ObjectProperty
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

        for setting in gv.db.get_settings(app.type):
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

    def open_template_settings(self):
        dialog = MDDialog(
            auto_dismiss=False,
            title=f"Настройки шаблонов и координат",
            type="custom",
            content_cls=TemplateBox(),
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


class TemplateBox(MDScrollView):

    dialog_parent = ObjectProperty()

    def __init__(self, **kwargs):
        super(TemplateBox, self).__init__(**kwargs)
        self.update_data()

    def update_data(self, *args):
        self.ids.templates.clear_widgets()

        for template in gv.db.get_template_settings(app.type):
            self.ids.templates.add_widget(
                TemplateRow(
                    hint_text=template['key'],
                    icon="trash-can",
                    icon_func=self.delete_row,
                    icon_right="vector-point-edit",
                    icon_right_func=print,
                    text=template['value'],
                    type=template['type']
                )
            )

        self.ids.templates.add_widget(TemplateRow(hint_text="Добавить", icon="plus", icon_func=self.add_row))

    def save_data(self, *args):
        templates = [(app.type,
                      template.hint_text,
                      template.text,
                      template.type)
                     for template in self.ids.templates.children if template.type]

        gv.db.save_template_settings(templates)

    def delete_row(self, row):
        self.ids.templates.remove_widget(row)
        Clock.schedule_once(self.dialog_parent.update_height)

    def add_row(self, instance):
        self.ids.templates.add_widget(
            TemplateRow(
                hint_text=instance.ids.tf.text,
                icon="trash-can",
                icon_func=self.delete_row,
                icon_right="vector-point-edit",
                icon_right_func=print,
                type="region"
            ),
            1
        )

        Clock.schedule_once(self.dialog_parent.update_height)


class TemplateRow(MDBoxLayout):
    text = StringProperty()
    hint_text = StringProperty()
    icon = StringProperty()
    icon_func = ObjectProperty()
    icon_right = StringProperty()
    icon_right_func = ObjectProperty()
    type = StringProperty()

    def __init__(self, **kwargs):
        super(TemplateRow, self).__init__(**kwargs)
        self.ids.tf.bind(on_touch_down=self.on_press_textfield_right_icon)

    def on_press_textfield_right_icon(self, instance, touch):
        """
        Обработчик нажатия в область иконки текстового поля. Так как иконка - это не объект, а просто текстура
        (картинка), от событие срабатывает, когда: нажатие попало в объект текстового поля, нажатие правее позиции
        картинки. Расчет позиции картинки взял из kivymd/uix/textfield/textfield.kv
        """
        tf = self.ids.tf  # Объект текстового поля
        if not self.icon_right or not tf.collide_point(*touch.pos):  # Входит ли клик в объект текстового поля
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
