"""
Текущее состояние:
База данных временно откручена, все настройки находятся в config.ini, для совместимости пустая БД должна быть в папке
Список actions находится в actions.json
"""

# Настройки окна, должны быть до импорта графических объектов
from kivy.config import Config
from kivy.core.window import Window

Config.set('graphics', 'resizable', '1')
Config.set('graphics', 'width', '1200')
Config.set('graphics', 'height', '600')

# Общие
from datetime import datetime
import json
import random
import sqlite3
import textwrap
import threading

# Киви
from kivy.animation import Animation
from kivy.clock import Clock, mainthread
from kivy.metrics import sp, dp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty, OptionProperty, \
    ObjectProperty, DictProperty

# Киви МД
from kivymd.app import MDApp
from kivymd.uix.behaviors import RoundedRectangularElevationBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRectangleFlatButton, MDRectangleFlatIconButton, MDFlatButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import OneLineAvatarListItem, OneLineIconListItem
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.snackbar import Snackbar

# Из проекта
from allignedtextinput import AlignedTextInput
import gv
import actions
import additional_functional

app = MDApp.get_running_app()


class ControlPanelApp(MDApp):
    _anim_timer = None
    type_options = {
        'B': {
            'icon': 'alpha-b-box-outline',
            'buttons': [
                {
                    'text': "Настройки цен",
                    'icon': 'calculator-variant-outline',
                    'content_cls': additional_functional.Items
                },
                {
                    'text': "Очередь сделок",
                    'icon': 'format-list-numbered',
                    'content_cls': additional_functional.Deals
                },
                {
                    'text': "Черный список",
                    'icon': 'playlist-remove',
                    'content_cls': None
                },
                {
                    'text': "Статистика",
                    'icon': 'calendar-month',
                    'content_cls': None
                },
            ]
        },
        'S': {
            'icon': 'alpha-s-box-outline',
            'buttons': [
                {
                    'text': "Настройки цен",
                    'icon': 'calculator-variant-outline',
                    'content_cls': None
                },
                {
                    'text': "Очередь сделок",
                    'icon': 'human-queue',
                    'content_cls': None
                },
                {
                    'text': "Черный список",
                    'icon': 'playlist-remove',
                    'content_cls': None
                },
                {
                    'text': "Статистика",
                    'icon': 'calendar-month',
                    'content_cls': None
                },
            ]
        },
        'F1': {
            'icon': 'keyboard-f1',
            'buttons': [
                {
                    'text': "Статистика",
                    'icon': 'calendar-month',
                    'content_cls': None
                },
            ]
        }
    }
    _types = list(type_options.keys())
    action_thread = ObjectProperty()
    action_variables = DictProperty()
    actions = DictProperty()
    current_action = ObjectProperty()
    current_stage = ObjectProperty()
    variables = DictProperty({})
    first_run_animation_completed = BooleanProperty(True)
    main = None
    need_pause = BooleanProperty(False)
    need_stop_action = BooleanProperty(False)
    status = StringProperty("Я родился")
    running = BooleanProperty(False)
    type = OptionProperty(_types[0], options=_types)
    timer = NumericProperty(0)

    def __init__(self, **kwargs):
        super(ControlPanelApp, self).__init__(**kwargs)

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Orange"
        if not self.main:
            self.main = MainScreen()
        return self.main

    def change_type(self):
        if self.running:
            Snackbar(text="Бот работает. Сначала нужно остановить бота").open()
            return

        try:
            self.type = self._types[self._types.index(self.type) + 1]
        except IndexError:
            self.type = self._types[0]

        self.main.upload_buttons()
        self.main.ids.action_tab.fill_default_stages()
        self.update_action_variables()

    @mainthread
    def do_next_action(self, go_to=None):
        self.main.ids.action_tab.do_next_action(go_to)

    def on_start(self):
        if not self.init_config():
            return

        super(ControlPanelApp, self).on_start()

        global app
        app = MDApp.get_running_app()

        self._update_timer(True, False)
        self.upload_actions()
        self.main.upload_buttons()
        self.update_action_variables()

    def init_config(self):
        try:
            gv.upload_config()
            return True
        except sqlite3.OperationalError as e:
            error_message = textwrap.dedent(f"""\
                Ошибка при подключении или создании БД:
                {e}
                Сейчас программа будет закрыта""")
        except FileNotFoundError:
            error_message = textwrap.dedent("""\
                Файл config.ini не найден в папке программы\n
                Сейчас программа будет закрыта""")

        dialog = MDDialog(
            auto_dismiss=False,
            text=error_message,
            buttons=[
                MDRectangleFlatButton(
                    text="OK",
                    on_release=lambda *_: self.stop()
                ),
            ],
        )
        Clock.schedule_once(lambda *_: dialog.open())
        return False

    def _on_complete_timer(self, *args):
        if self.running:
            if self.action_thread and self.action_thread.is_alive():
                self.set_status(f"Останавливаюсь по времени. Заканчиваю последний цикл")
                self.need_pause = True
            else:
                self.set_running(False)
        else:
            self.set_running(True)
            self.do_next_action(0)

    def upload_actions(self):
        with open('actions.json', encoding='utf-8') as f:
            _actions = json.load(f)

        for list_actions in _actions.values():
            for i, action in enumerate(list_actions):
                action.update({
                    'opacity': 0 if not app.first_run_animation_completed else 1,
                    '_anim': False,
                    'active': False,
                    'index': i,
                    '_timer': action['timer'] if ('timer' in action) else 0,
                    'have_timer': 'timer' in action
                })

                for j, stage in enumerate(action['stages']):
                    stage.update({
                        'index': j,
                        'status': 'queue'
                    })

        self.actions = _actions
        self.main.ids.action_tab.fill_default_stages()

    def update_action_variables(self):
        def _value(row):
            if row['type'] == 'template':
                return f"{self.type}/{row['window_resolution']}/{row['value']}"
            elif row['type'] == 'region' or row['type'] == 'coord':
                return list(map(int, row['value'].split(", ")))
            else:
                return row['value']

        self.action_variables = {row['key']: _value(row) for row in gv.db.get_action_variables(app.type)}

    def set_status(self, status, append_current_action=False, append_current_stage=False):
        if append_current_stage:
            status = f"[{self.current_stage.text}] " + status
        if append_current_action:
            status = f"[{self.current_action.name}] " + status
        self.status = status

    @mainthread
    def set_running(self, value):
        if self.running == value:
            return

        self.running = value

        if self.running:
            self.need_pause = False
            self.set_status("Запускаюсь")
            self._update_timer(True)
        else:
            self.main.ids.action_tab.reset_actions_completed(True)
            if self.need_pause:
                if not self.timer:
                    self.set_status(f"Остановлен по времени (но дождался завершения действий)")
                else:
                    self.set_status(f"Остановлен по приказу (но дождался завершения действий)")
            else:
                if not self.timer:
                    self.set_status(f"Остановлен по времени (но действия уже были остановлены)")
                else:
                    self.set_status(f"Остановлен по приказу (но действия уже были остановлены)")
            self._update_timer(False)
            self.need_pause = False

    def update_current_action(self, action):
        self.action_thread = threading.Thread(target=lambda *_: actions.do_current_action(), daemon=True)
        self.current_action = action

    def update_current_stage(self, stage):
        self.current_stage = stage

    def _update_timer(self, for_work, need_start=True):
        if self._anim_timer:
            self._anim_timer.cancel(self)

        if for_work:
            setting_timer = gv.db.get_settings(app.type, "setting_textfield_working")
        else:
            setting_timer = gv.db.get_settings(app.type, "setting_textfield_pause")
        _timer = random.randint(*map(int, setting_timer[0]['value'].split(",")))

        self.timer = _timer
        self._anim_timer = Animation(timer=0, d=self.timer)
        self._anim_timer.bind(on_complete=self._on_complete_timer)
        if need_start:
            self._anim_timer.start(self)

    def _set_is_executor(self, checkbox, value):
        self.is_executor = value


class MainScreen(MDBoxLayout):
    stages = ListProperty([])
    log_finish = datetime.strptime("2030-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
    log_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def __init__(self, **kwargs):
        super(MainScreen, self).__init__(**kwargs)

    def first_run_animation_start(self):
        self.ids.action_tab.first_run_animation_start()

    def first_run_animation_after(self):
        app.first_run_animation_completed = True
        self.start_stop(True)

    def refresh_logs(self):
        self.log_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_finish = datetime.strptime("2030-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
        self.fill_logs()

    def refresh_settings(self):
        pass

    def start_stop(self, start):  # button callback
        if app.running == start:
            return

        if start:
            app.set_running(True)
            self.ids.action_tab.do_next_action(0)
            Snackbar(text="Запущен").open()
        else:
            if app.action_thread and app.action_thread.is_alive():
                app.set_status(f"Останавливаюсь. Заканчиваю последний цикл")
                app.need_pause = True
                Snackbar(text="Буду остановлен после завершения последнего действия").open()
            else:
                app.set_running(False)
                Snackbar(text="Остановлен").open()

    def update_logs(self):
        try:
            self.log_start = datetime.strptime(self.ids.log_start.text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            Snackbar(text="Дата начала периода должна быть заполнена и введена в формате 2022-04-24 07:24:26").open()
            return
        if self.ids.log_finish.text:
            try:
                self.log_finish = datetime.strptime(self.ids.log_finish.text, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                Snackbar(text="Дата окончания периода должна быть введена в формате 2022-04-24 07:24:26").open()
                return

        self.fill_logs()
        self.ids.logs_box.scroll_y = 0

    def upload_buttons(self):
        buttons = self.ids.action_tab.ids.buttons
        buttons.clear_widgets()

        for button_setting in app.type_options[app.type]['buttons']:
            button = CustomMDRectangleFlatIconButton()
            button.content_cls = button_setting['content_cls']
            button.opacity = 0 if not app.first_run_animation_completed else 1
            button.icon = button_setting['icon']
            button.size_hint_x = 1
            button.text = button_setting['text']
            button.bind(on_release=self.on_action_button)
            buttons.add_widget(button)

    def fill_logs(self):
        self.ids.logs_box.data = [{
            'text': "Тестовый текст лога " + str(x),
            'character': "snckmykek_q_test123",
            'trade_id': "ADkjN28OI2ni4",
            'level': x % 4 if x % 4 != 0 else 1,
            'item': "Foreboding Delirium Orb",
            'datetime': datetime.now().strftime("%b %d %H:%M:%S"),
        } for x in range(10000)]

    def on_tab_switch(
            self, instance_tabs, instance_tab, instance_tab_label, tab_text
    ):
        if instance_tab.tab_label_text == "Настройки":
            instance_tab.children[0].refresh_settings()

    def on_action_button(self, instance):

        if instance.content_cls is None:
            Snackbar(text="Еще не работает:)").open()
            return

        content = instance.content_cls()

        dialog = additional_functional.CustomDialog(
            auto_dismiss=False,
            title=content.title,
            type="custom",
            content_cls=content,
            buttons=[
                MDRectangleFlatIconButton(
                    icon=dialog_button['icon'],
                    text=dialog_button['text'],
                    theme_text_color="Custom",
                    text_color=app.theme_cls.primary_color,
                    on_release=dialog_button['on_release']
                ) for dialog_button in content.buttons
            ],
        )

        dialog.content_cls.dialog_parent = dialog
        dialog.bind(on_pre_open=content.on_pre_open)
        dialog.open()


class LogBox(MDBoxLayout):
    level = NumericProperty(1)
    icons = [
        ("numeric-1-circle-outline", [.28, .60, .92, 1]),
        ("numeric-2-circle-outline", [.94, .45, .15, 1]),
        ("numeric-3-circle-outline", [1, 0, 0, 1])
    ]
    datetime = StringProperty()
    character = StringProperty()
    trade_id = StringProperty()
    item = StringProperty()
    text = StringProperty()

    def __init__(self, **kwargs):
        super(LogBox, self).__init__(**kwargs)


class OneLineQueue(OneLineIconListItem):
    index = NumericProperty(0)
    left_widget_source = StringProperty("")
    status = OptionProperty('queue', options=['queue', 'progress', 'completed', 'error'])
    widgets = {
        'queue': 'sleep',
        'progress': 'play-circle-outline',
        'completed': 'check',
        'error': 'close-circle'
    }


class MiniCheckBox(MDCheckbox):

    def __init__(self, **kwargs):
        super(MiniCheckBox, self).__init__(**kwargs)
        Clock.schedule_once(lambda *_: self._rewrite_anim())

    def _rewrite_anim(self):
        self.check_anim_in = Animation(
            font_size=sp(16), duration=0.1, t="out_quad"
        )


class DatetimeTextInput(AlignedTextInput):
    def insert_text(self, substring, from_undo=False):
        if len(self.text) > 18:
            return super().insert_text("", from_undo=from_undo)
        else:
            return super().insert_text(substring, from_undo=from_undo)


class CustomMDRectangleFlatIconButton(MDRectangleFlatIconButton):
    content_cls = None


if __name__ == "__main__":
    ControlPanelApp().run()
    app = MDApp.get_running_app()
