"""
Текущее состояние:
База данных временно откручена, все настройки находятся в config.ini, для совместимости пустая БД должна быть в папке
Список actions находится в actions.json
"""

# Настройки окна, должны быть до импорта графических объектов
import json

from kivy.config import Config

Config.set('graphics', 'resizable', '1')
Config.set('graphics', 'width', '1200')
Config.set('graphics', 'height', '600')

# Общие
from datetime import datetime
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
from kivymd.uix.button import MDRectangleFlatButton, MDRectangleFlatIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import OneLineAvatarListItem, OneLineIconListItem
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.snackbar import Snackbar

# Из проекта
from allignedtextinput import AlignedTextInput
import gv
import actions

app = MDApp.get_running_app()


class ControlPanelApp(MDApp):
    _anim_timer = None
    _type_options = {'B': 'alpha-b-box-outline', 'S': 'alpha-s-box-outline', 'F1': 'keyboard-f1'}
    _types = list(_type_options.keys())
    actions = DictProperty()
    action_thread = ObjectProperty()
    current_action = ObjectProperty()
    current_stage = ObjectProperty()
    first_run_animation_completed = BooleanProperty(True)
    main = None
    need_pause = BooleanProperty(False)
    need_stop_action = BooleanProperty(False)
    type = OptionProperty(_types[0], options=_types)
    timer = NumericProperty(0)
    start_over = BooleanProperty(True)
    status = StringProperty("Я родился")
    running = BooleanProperty(False)

    def __init__(self, **kwargs):
        self.action_thread = threading.Thread(target=lambda *_: actions.do_current_action(), daemon=True)

        if not self.init_config():
            return

        # Clock.schedule_interval(lambda *_: self.update_data(), 1)
        self._update_timer(True, False)

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

    @mainthread
    def do_next_action(self, go_to=None):
        self.action_thread = threading.Thread(target=lambda *_: actions.do_current_action(), daemon=True)
        self.main.ids.action_tab.do_next_action(go_to)

    def on_start(self):
        global app
        app = MDApp.get_running_app()

        self.upload_actions()
        self.main.upload_buttons()
        super(ControlPanelApp, self).on_start()

    def init_config(self):
        try:
            gv.upload_config()
            return True
        except sqlite3.OperationalError:
            error_message = textwrap.dedent(f"""\
                Не найдена БД с именем database.db в папке: {gv.db_path}.
                Изменить путь можно в файле config.ini в папке программы.
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
            self.set_running(True, True)
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

    def set_status(self, status, append_current_action=False, append_current_stage=False):
        if append_current_stage:
            status = f"[{self.current_stage.text}] " + status
        if append_current_action:
            status = f"[{self.current_action.name}] " + status
        self.status = status

    def set_running(self, value, start_over=False):
        if self.running == value:
            return

        self.running = value

        if self.running:
            self.need_pause = False
            self.set_status("Запускаюсь")
            self._update_timer(True)
            self.start_over = start_over
        else:
            self.main.ids.action_tab.reset_actions_completed()
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
            self.start_over = True

    def update_current_action(self, action):
        self.current_action = action

    def update_current_stage(self, stage):
        self.current_stage = stage

    def _update_timer(self, for_work, need_start=True):
        if self._anim_timer:
            self._anim_timer.cancel(self)
        self.timer = 13 if for_work else 10
        self._anim_timer = Animation(timer=0, d=self.timer)
        self._anim_timer.bind(on_complete=self._on_complete_timer)
        if need_start:
            self._anim_timer.start(self)

    def update_data(self):
        # stopped, status?
        pass

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

    def refresh_items(self):
        if app.type == 'B':
            self.ids.items_box.data = [{
                'name': f"item test (B) {i}",
            } for i in range(20)]
        elif app.type == 'S':
            self.ids.items_box.data = [{
                'name': f"item test (S) {i}",
            } for i in range(20)]

    def refresh_logs(self):
        self.log_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_finish = datetime.strptime("2030-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
        self.fill_logs()

    def refresh_settings(self):
        pass

    def set_use_all_items(self, value):
        for item in self.ids.items_list.children:
            item.use = value

    def start_stop(self, start):  # button callback
        if app.running == start:
            return

        if start:
            app.set_running(True, True)
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

        if app.type == "B":
            button = MDRectangleFlatIconButton()
            button.opacity = 0 if not app.first_run_animation_completed else 1
            button.icon = 'calculator-variant-outline'
            button.size_hint_x = 1
            button.text = "Настройки цен"
            button.bind(on_release=lambda *_: Snackbar(text="Еще не работает:)").open())
            buttons.add_widget(button)

            button = MDRectangleFlatIconButton()
            button.opacity = 0 if not app.first_run_animation_completed else 1
            button.icon = 'format-list-numbered'
            button.size_hint_x = 1
            button.text = "Очередь сделок"
            button.bind(on_release=lambda *_: Snackbar(text="Еще не работает:)").open())
            buttons.add_widget(button)

            button = MDRectangleFlatIconButton()
            button.opacity = 0 if not app.first_run_animation_completed else 1
            button.icon = 'playlist-remove'
            button.size_hint_x = 1
            button.text = "Черный список"
            button.bind(on_release=lambda *_: Snackbar(text="Еще не работает:)").open())
            buttons.add_widget(button)

            button = MDRectangleFlatIconButton()
            button.opacity = 0 if not app.first_run_animation_completed else 1
            button.icon = 'calendar-month'
            button.size_hint_x = 1
            button.text = "Статистика"
            button.bind(on_release=lambda *_: Snackbar(text="Еще не работает:)").open())
            buttons.add_widget(button)

        elif app.type == "S":
            button = MDRectangleFlatIconButton()
            button.opacity = 0 if not app.first_run_animation_completed else 1
            button.icon = 'calculator-variant-outline'
            button.size_hint_x = 1
            button.text = "Настройки цен"
            button.bind(on_release=lambda *_: Snackbar(text="Еще не работает:)").open())
            buttons.add_widget(button)

            button = MDRectangleFlatIconButton()
            button.opacity = 0 if not app.first_run_animation_completed else 1
            button.icon = 'human-queue'
            button.size_hint_x = 1
            button.text = "Очередь сделок"
            button.bind(on_release=lambda *_: Snackbar(text="Еще не работает:)").open())
            buttons.add_widget(button)

            button = MDRectangleFlatIconButton()
            button.opacity = 0 if not app.first_run_animation_completed else 1
            button.icon = 'playlist-remove'
            button.size_hint_x = 1
            button.text = "Черный список"
            button.bind(on_release=lambda *_: Snackbar(text="Еще не работает:)").open())
            buttons.add_widget(button)

            button = MDRectangleFlatIconButton()
            button.opacity = 0 if not app.first_run_animation_completed else 1
            button.icon = 'calendar-month'
            button.size_hint_x = 1
            button.text = "Статистика"
            button.bind(on_release=lambda *_: Snackbar(text="Еще не работает:)").open())
            buttons.add_widget(button)

        elif app.type == "F1":
            button = MDRectangleFlatIconButton()
            button.opacity = 0 if not app.first_run_animation_completed else 1
            button.icon = 'calendar-month'
            button.size_hint_x = 1
            button.text = "Статистика"
            button.bind(on_release=lambda *_: Snackbar(text="Еще не работает:)").open())
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


class ItemBox(MDBoxLayout):
    use = BooleanProperty(False)
    name = StringProperty("Name")
    max_price = NumericProperty(0)
    bulk_price = NumericProperty(0)
    qty = NumericProperty(0)

    def __init__(self, **kwargs):
        super(ItemBox, self).__init__(**kwargs)


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


if __name__ == "__main__":
    ControlPanelApp().run()
    app = MDApp.get_running_app()
