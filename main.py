"""
Приложение работает в основном потоке, действия выполняются в других потоках.
Любая кнопка запуска всегда обращается к функции приложения, которое делает 2 вещи: отображает графически запуск
    действия (запускает таймер и прочее) и запускает поток с функцией этапа действия.
Останавливать действие (отображать это графически) может только функция этапа по своему окончанию (вызывает функцию
    app.on_complete_stage в основном потоке). Функция может закончиться
    в 3 случаях: выполнена, ошибка, просьба от приложения из основного потока (То есть для досрочной остановки действия,
    нужно поднять флаг app.need_stop_action).
"""

# Настройки окна, должны быть до импорта графических объектов
import os
import time

import keyboard
from kivy.config import Config
from pip._internal.operations.freeze import freeze

from common import resource_path

Config.set('graphics', 'resizable', '1')
Config.set('graphics', 'width', '1200')
Config.set('graphics', 'height', '900')

# Общие
from datetime import datetime, timezone, timedelta
import configparser
import random
import sqlite3
import textwrap
import threading
import traceback

# Киви
from kivy.animation import Animation
from kivy.clock import Clock, mainthread
from kivy.metrics import sp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty, OptionProperty, \
    ObjectProperty, DictProperty

# Киви МД
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRectangleFlatButton, MDRectangleFlatIconButton, MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import OneLineIconListItem, OneLineAvatarListItem
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.snackbar import Snackbar

# Из проекта
from allignedtextinput import AlignedTextInput
from bots import bots_list
from task_tab import TaskBox, Stages
from db_requests import Database
from setting_tab import AppSettingTab, BotSettingTab  # для pyinstaller импорт тут, а не в controllpanel.kv


app = MDApp.get_running_app()


class ControlPanelApp(MDApp):
    v = "0.2.0"

    _anim_timer = None
    bot = ObjectProperty()
    bots = ListProperty()
    current_task = NumericProperty(0)
    current_stage = NumericProperty(0)
    db = None
    db_path = ""
    error_detail = StringProperty()
    extended_task = NumericProperty(0)
    first_run_animation_completed = BooleanProperty(True)
    freeze = BooleanProperty(False)
    main = None
    need_break = BooleanProperty(False)
    need_stop_task = BooleanProperty(False)
    stages_box = ObjectProperty()
    status = StringProperty(f"Бот-платформа {v}")
    state = StringProperty('break', options=['break', 'work'])
    tasks_obj = ListProperty([])
    timer = NumericProperty(0)
    _handbrake = False  # TODO Временное решение, нужно отслеживать, поставился ли need_stop_task вручную или программно

    def __init__(self, **kwargs):
        super(ControlPanelApp, self).__init__(**kwargs)
        self.bots = bots_list

    def set_hotkeys(self):

        # hotkey_stop_action
        @mainthread
        def set_need_stop_task():
            self.need_stop_task = True

        hotkey = self.s('any', 'hotkey_stop_action')
        if not hotkey:
            hotkey = "f11"
        keyboard.add_hotkey(hotkey, set_need_stop_task)

        # hotkey_freeze
        @mainthread
        def set_freeze():
            self.freeze = True

        hotkey = self.s('any', 'hotkey_freeze')
        if not hotkey:
            hotkey = "alt+f11"
        keyboard.add_hotkey(hotkey, set_freeze)

        # hotkey_break
        @mainthread
        def work_break():
            self.request_break() if self.state == 'work' else self.start()

        hotkey = self.s('any', 'hotkey_break')
        if not hotkey:
            hotkey = "f12"
        keyboard.add_hotkey(hotkey, work_break)

        # hotkey_close
        @mainthread
        def instant_exit():
            os._exit(0)

        hotkey = self.s('any', 'hotkey_close')
        if not hotkey:
            hotkey = "alt+f12"
        keyboard.add_hotkey(hotkey, instant_exit)

    def add_task_buttons(self):
        buttons = self.main.ids.task_tab.ids.buttons
        buttons.clear_widgets()

        for button_setting in self.bot.get_task_tab_buttons_settings():
            button = MDRectangleFlatIconButton()
            button.opacity = 0 if not app.first_run_animation_completed else 1
            button.icon = button_setting['icon']
            button.size_hint_x = 1
            button.text = button_setting['text']
            button.bind(on_release=button_setting['func'])

            buttons.add_widget(button)

    def add_task_content(self):
        self.main.ids.task_tab.ids.content.clear_widgets()

        if self.bot.task_tab_content:
            self.main.ids.task_tab.ids.content.add_widget(self.bot.task_tab_content)

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Orange"
        if not self.main:
            self.main = MainScreen()
        return self.main

    def choose_bot(self):
        if self.state != 'break':
            Snackbar(text="Сменить бота можно только во время перерыва").open()
            return

        dialog = MDDialog(
            title="Доступные боты",
            type="simple",
            items=[BotChangeItem(
                bot_class=bot_class,
                icon=bot_class.icon,
                text=bot_class.name,
                on_release=lambda obj: self.set_bot(obj.bot_class)
            ) for bot_class in self.bots],
        )

        for item in dialog.items:
            item.bind(on_release=dialog.dismiss)

        dialog.open()

    def execute_current_stage(self, *args):
        stage = self.bot.tasks[self.current_task]['stages'][self.current_stage]

        if self.s(self.bot.key, 'test'):
            time.sleep(1)

        _start = datetime.now()

        try:
            self.bot.set_empty_log()
            self.bot.set_freeze(False)
            error = stage['func']()
            if error:
                self.bot.update_log(level=2, text=error)
        except Exception as e:
            error = str(e)
            self.error_detail = traceback.format_exc()
            self.bot.update_log(details=self.error_detail, level=1, text=error)

            # TODO Временно тут
            try:
                self.bot.update_deal_history(last_stage=",".join([self.current_task, self.current_stage]))
            except:
                pass

        result = None

        if error:
            result = {'text': error}
            if stage.get('on_error'):
                result.update(stage.get('on_error'))

            # Пока написано тут, но в будущем нужно в бота вообще всю эту функцию перенести
            #  (это относится только к конкретному боту, а не к любому)
            try:
                self.bot.update_deal_history(error=error)
            except:
                pass

        # TODO Временное решение, нужен более гибкий функционал записи времени выполнения участков этапов
        self.db.save_stage_lead_time(
            (_start.timestamp(), stage['name'], (datetime.now() - _start).total_seconds(), not error)
        )

        self.on_complete_stage(self, error=result)

    def display_stages(self, new_extended_task):

        def change_extended_task(need_extend):
            self.tasks_obj[self.extended_task].ids.content.clear_widgets()

            if need_extend:
                self.extended_task = new_extended_task
                self.tasks_obj[self.extended_task].ids.content.add_widget(self.stages_box)
                Animation(height=self.stages_box.calculate_height(), d=.1).start(self.stages_box)

        task = self.tasks_obj[self.extended_task]
        if task.extended:
            anim = Animation(height=0, d=.1)
            anim.bind(on_complete=lambda *_: change_extended_task(new_extended_task != self.extended_task))
            anim.start(self.stages_box)
        else:
            change_extended_task(True)

    def init_config(self):
        try:
            config = configparser.ConfigParser(inline_comment_prefixes="#")
            if not config.read(resource_path('config.ini')):
                raise FileNotFoundError

            self.db_path = config['common']['db_path']
            self.db = Database(os.path.join(self.db_path, 'main.db'))

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

    @mainthread
    def on_complete_stage(self, obj, error=None):

        _debug = self.s(self.bot.key, 'debug')
        if self.need_stop_task or _debug or error is not None:  # Нужно остановить задачи
            # Статус текущего этапа
            self.stages_box.set_current_status('error' if error else 'stopped')

            # Деактивация визуала текущей задачи
            if self.tasks_obj[self.current_task].active:
                self.tasks_obj[self.current_task].stop()

            error_text, goto = "", None
            if isinstance(error, str):
                error_text = error
            elif isinstance(error, dict):
                if error.get('text'):
                    error_text = error.get('text')
                if error.get('func'):
                    error.get('func')()
                goto = error.get('goto')

            if error_text:
                self.set_status(f"Ошибка: {error_text}", True, True)
                self.bot.save_log()
            elif _debug:
                self.set_status(f"Остановлен: Debug (не запускать следующий этап)", True, True)
            elif self.need_stop_task:
                self.set_status(f"Остановлен: Вручную или по времени", True, True)

            if self.need_break:
                self.request_break()
                return

            if goto and not _debug and not self._handbrake:
                self.start_stage(goto)

        else:  # Запускаем следующий этап
            self.start_stage()

    def on_complete_timer(self, *args):
        if self.state == 'work':
            self.request_break()
        else:
            self.start()

    def on_start(self):
        if not self.init_config():
            return

        global app
        app = MDApp.get_running_app()

        self.stages_box = Stages()

        current_bot = self.s('any', 'current_bot')
        if current_bot:
            self.set_bot(current_bot)
        else:
            self.choose_bot()

        self.set_hotkeys()

    def open_status(self):
        dialog = MDDialog(
            title=self.status,
            text=self.error_detail,
            buttons=[
                MDFlatButton(
                    text="OK",
                    theme_text_color="Custom",
                    text_color=self.theme_cls.primary_color,
                ),
            ],
        )
        dialog.buttons[0].bind(on_release=dialog.dismiss)
        dialog.open()

    def reset_tasks_completed(self):
        for task in self.tasks_obj:
            task.completed_once = False

    def request_break(self):
        if self.tasks_obj[self.current_task].active:
            self.need_break = True
        else:
            self.stop()

    def s(self, bot_name, setting_key):
        """Получить настройку (setting)"""
        return self.db.get_setting(bot_name, setting_key)

    def set_bot(self, bot):
        """Устанавливает текущего бота по имени или классу и обновляет зависимые данные"""

        if isinstance(bot, str):  # По имени бота
            self.bot = list(filter(lambda b: b.key == bot, self.bots))[0]()
        else:  # По классу бота
            self.bot = bot()

        self.db.save_settings([('any', 'current_bot', self.bot.key, 'str')])

        self.set_status(self.bot.name)
        self.add_task_buttons()
        self.add_task_content()
        self.upload_tasks()
        self.main.ids.app_settings.refresh_settings()
        self.main.ids.bot_settings.refresh_settings()

    def set_current_stage(self, goto: list = None):

        def next_available_task(index):
            for task in self.tasks_obj:
                if task.index > index and task.available():
                    return task

        if goto is not None:  # Указано, к какому этапу надо перейти
            self.current_task = goto[0]
            self.current_stage = goto[1]
            return True

        # Есть следующий этап в задаче
        if self.current_stage < len(self.tasks_obj[self.current_task].stages) - 1:
            self.current_stage += 1
            return True

        next_task = next_available_task(self.current_task)
        if not next_task:  # Это было последнее доступное действие
            if not self.need_break:
                next_task = next_available_task(-1)

        if next_task:
            self.current_task = next_task.index
            self.current_stage = 0
            return True

    def start(self, goto=(0, 0)):
        self.need_stop_task = False
        self.reset_tasks_completed()
        self.set_state('work')
        self.start_stage(goto)

    def start_by_task(self, goto):
        self.need_stop_task = False
        self.reset_tasks_completed()
        self.set_tasks_completed(goto[0])
        self.set_state('work')
        self.start_stage(goto)

    def start_stage(self, goto=None):
        if self.state != 'work':
            self.start(goto)
            return

        self._handbrake = False

        _current_task = self.current_task
        if self.set_current_stage(goto):

            # Если изменилась задача, то по визуалу останавливаем старую
            if self.current_task != _current_task:
                self.tasks_obj[_current_task].stop()

            self.error_detail = "Нет деталей ошибки"
            self.need_stop_task = False
            self.set_status("Выполняю", True, True)

            # В любом случае запускаем текущую, если не запущена
            if not self.tasks_obj[self.current_task].active:
                self.tasks_obj[self.current_task].start()
            # Обновить таймер в случае, когда с помощью goto запущена та же самая задача, но с другого этапа
            elif goto is not None or (self.current_task == _current_task and self.current_stage == 0):
                self.tasks_obj[self.current_task].start_timer()

            # Статус текущего этапа
            self.stages_box.set_current_status('progress')

            # В любом случае запускаем след этап
            threading.Thread(target=self.execute_current_stage, daemon=True).start()
        else:
            if self.tasks_obj[self.current_task].active:
                self.tasks_obj[_current_task].stop()
            if self.tasks_obj[self.extended_task].extended:
                self.display_stages(self.extended_task)

            self.stop()

    def stop(self):
        self.reset_tasks_completed()
        self.set_state('break')

    def set_status(self, status, append_current_action=False, append_current_stage=False):
        if append_current_stage:
            status = f"[{self.tasks_obj[self.current_task].stages[self.current_stage]['text']}] {status}"
        if append_current_action:
            status = f"[{self.tasks_obj[self.current_task].name}] {status}"
        self.status = status

    def set_state(self, new_state):
        if self.state == new_state:
            return

        self.state = new_state

        self.need_break = False
        self.set_timer()

        if self.state == 'work':
            self.set_status("Запускаюсь")
        elif self.state == 'break':
            self.set_status(f"Остановлен на перерыв")

    def set_tasks_completed(self, index=0):
        for task in self.tasks_obj:
            if task.index < index:
                task.completed_once = True

    def set_timer(self):
        if self._anim_timer:
            self._anim_timer.cancel(self)

        if self.state == 'work':
            setting_timer = self.db.get_setting(self.bot.key, "bot_working")
        elif self.state == 'break':
            setting_timer = self.db.get_setting(self.bot.key, "bot_break")
        else:
            return

        self.timer = random.randint(*map(int, setting_timer.split(",")))
        self._anim_timer = Animation(timer=0, d=self.timer)
        self._anim_timer.bind(on_complete=self.on_complete_timer)
        self._anim_timer.start(self)

    def upload_tasks(self):
        self.current_task = 0
        self.current_stage = 0
        self.extended_task = 0
        self.stages_box = Stages()

        self.tasks_obj.clear()
        for i, task_setting in enumerate(self.bot.tasks):

            self.tasks_obj.append(
                TaskBox(
                    available_mode=task_setting['available_mode'],
                    index=i,
                    name=task_setting['name'],
                    opacity=0 if not app.first_run_animation_completed else 1,
                    task_time=task_setting['timer'],
                    stages=[
                        {
                            'index': j,
                            'text': stage['name'],
                            'status': 'queue'
                        } for j, stage in enumerate(task_setting['stages'])]
                )
            )

        self.main.ids.task_tab.ids.tasks_parent.clear_widgets()
        for task_obj in self.tasks_obj:
            self.main.ids.task_tab.ids.tasks_parent.add_widget(task_obj)

    def upload_variables(self):
        def _value(row):
            if row['type'] == 'template':
                values = row['value'].split(", ")
                return {
                    'relative': (row['window_resolution'] == 'relative'),
                    'path': f"{self.bot.key}/{row['window_resolution']}/{values[0]}",
                    'size': list(map(float, values[1:3]))
                }
            elif row['type'] == 'region' or row['type'] == 'coord':
                return {
                    'relative': (row['window_resolution'] == 'relative'),
                    'value': list(map(float, row['value'].split(", ")))
                }
            elif row['type'] == 'coord_list':
                coord_list = list(map(float, row['value'].split(", ")))
                return {
                    'relative': (row['window_resolution'] == 'relative'),
                    'value': zip(coord_list[::2], coord_list[1::2])
                }
            else:
                return row['value']

        self.bot._variables = {row['key']: _value(row) for row in gv.db.get_variables(self.bot.key)}


class MainScreen(MDBoxLayout):
    stages = ListProperty([])
    log_finish = datetime.strptime("2030-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
    log_start = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")

    def __init__(self, **kwargs):
        super(MainScreen, self).__init__(**kwargs)

    def fill_logs(self):
        tz = datetime.now().astimezone().tzinfo
        self.ids.logs_box.data = [{
            'datetime': datetime.fromtimestamp(row['date']).astimezone(tz).strftime("%b %d %H:%M:%S"),
            'level': row['level'],
            'text': row['text']
        } for row in app.db.get_logs(
            app.bot.key,
            int(self.log_start.timestamp()),
            int(self.log_finish.timestamp())
        )]

    def first_run_animation_after(self):
        app.first_run_animation_completed = True
        self.start_stop(True)

    def first_run_animation_start(self):
        self.ids.task_tab.first_run_animation_start()

    def on_tab_switch(
            self, instance_tabs, instance_tab, instance_tab_label, tab_text
    ):
        # if instance_tab.tab_label_text == "Настройки":
        #     instance_tab.children[0].refresh_settings()
        pass

    def refresh_settings(self):
        pass

    def start_stop(self, start):  # button callback
        if app.running == start:
            return

        if start:
            app.set_running(True)
            self.ids.task_tab.do_next_action(0)
            Snackbar(text="Запущен").open()
        else:
            if app.action_thread and app.action_thread.is_alive():
                app.set_status(f"Останавливаюсь. Заканчиваю последний цикл")
                app.need_break = True
                Snackbar(text="Буду остановлен после завершения последнего действия").open()
            else:
                app.set_running(False)
                Snackbar(text="Остановлен").open()

    def update_logs(self):
        try:
            self.log_start = datetime.strptime(self.ids.log_start.text, "%Y-%m-%d %H:%M:%S").astimezone()
        except ValueError:
            Snackbar(text="Дата начала периода должна быть заполнена и введена в формате 2022-04-24 07:24:26").open()
            return
        if self.ids.log_finish.text:
            try:
                self.log_finish = datetime.strptime(self.ids.log_finish.text, "%Y-%m-%d %H:%M:%S").astimezone()
            except ValueError:
                Snackbar(text="Дата окончания периода должна быть введена в формате 2022-04-24 07:24:26").open()
                return

        self.fill_logs()
        self.ids.logs_box.scroll_y = 0


class LogBox(MDBoxLayout):
    level = NumericProperty(1)
    icons = [
        ("numeric-1-circle-outline", [.28, .60, .92, 1]),
        ("numeric-2-circle-outline", [.94, .45, .15, 1]),
        ("numeric-3-circle-outline", [1, 0, 0, 1])
    ]
    datetime = StringProperty()
    text = StringProperty()

    def __init__(self, **kwargs):
        super(LogBox, self).__init__(**kwargs)


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


class BotChangeItem(OneLineAvatarListItem):
    bot_class = ObjectProperty()
    divider = None
    icon = StringProperty()


if __name__ == "__main__":
    ControlPanelApp().run()
    app = MDApp.get_running_app()
