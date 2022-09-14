"""
Текущее состояние:
База данных временно откручена, все настройки находятся в config.ini, для совместимости пустая БД должна быть в папке
Список actions находится в actions.json
"""

# Настройки окна, должны быть до импорта графических объектов
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
    ObjectProperty

# Киви МД
from kivymd.app import MDApp
from kivymd.uix.behaviors import RoundedRectangularElevationBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRectangleFlatButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import OneLineAvatarListItem, OneLineIconListItem
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.snackbar import Snackbar

# Из проекта
from allignedtextinput import AlignedTextInput
import glob1
import poe_actions


class ControlPanelApp(MDApp):
    _anim_timer = None
    _type_options = ['B', 'S']
    actions = ListProperty([])
    action_thread = ObjectProperty()
    current_action = ObjectProperty()
    current_stage = ObjectProperty()
    fuckin_good_completed = BooleanProperty(True)
    main = None
    need_pause = BooleanProperty(False)
    need_stop_action = BooleanProperty(False)
    type = OptionProperty(_type_options[0], options=_type_options)
    timer = NumericProperty(0)
    start_over = BooleanProperty(True)
    status = StringProperty("Я родился")
    running = BooleanProperty(False)
    is_executor = BooleanProperty(True)

    def __init__(self, **kwargs):
        super(ControlPanelApp, self).__init__(**kwargs)

        global app
        app = MDApp.get_running_app()

        if not self.init_config():
            return

        # Clock.schedule_interval(lambda *_: self.update_data(), 1)
        self._update_timer(True, False)

    def on_start(self):
        self.upload_actions()
        super(ControlPanelApp, self).on_start()

    def init_config(self):
        try:
            glob1.upload_config()
            return True
        except sqlite3.OperationalError:
            error_message = textwrap.dedent(f"""\
                Не найдена БД с именем database.db в папке: {glob.db_path}.
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
            self.type = self._type_options[self._type_options.index(self.type) + 1]
        except IndexError:
            self.type = self._type_options[0]

    def _on_complete_timer(self, *args):
        if self.running:
            if self.action_thread and self.action_thread.is_alive():
                self.set_status(f"Останавливаюсь по времени. Заканчиваю последний цикл")
                self.need_pause = True
            else:
                self.set_running(False)
        else:
            self.set_running(True, True)
            self.main.do_next_action(0)

    def upload_actions(self):
        if app.type == 'B':
            stages = []
            self.actions = [
                {'opacity': 0 if not app.fuckin_good_completed else 1,
                 '_anim': False,
                 'active': False,
                 'index': 0,
                 'name': "Вход",
                 'func': "poe_actions.simulacrum(action.stages)",
                 '_timer': 30,
                 'have_timer': False,
                 'stages': [
                     {
                         'func': "start_poe()",
                         'index': 0,
                         'text': f"Запуск ПОЕ",
                         'status': 'queue'
                     },
                     {
                         'func': "authorization()",
                         'index': 1,
                         'text': f"Авторизация",
                         'status': 'queue'
                     },
                     {
                         'func': "choice_character()",
                         'index': 2,
                         'text': f"Выбор перса",
                         'status': 'queue'
                     },
                 ],
                 'only_start_over': True,
                 'only_before_pause': False
                 },

                {'opacity': 0 if not app.fuckin_good_completed else 1, '_anim': False, 'active': False, 'index': 1,
                 'name': "Действие 2", 'only_start_over': False, 'stages': stages, 'only_before_pause': False,
                 'func': "poe_actions.simulacrum(action.stages)", '_timer': 60, 'have_timer': False},
                {'opacity': 0 if not app.fuckin_good_completed else 1, '_anim': False, 'active': False, 'index': 2,
                 'name': "Действие 3", 'only_start_over': False, 'stages': stages, 'only_before_pause': False,
                 'func': "poe_actions.simulacrum(action.stages)", '_timer': 90, 'have_timer': False},
                {'opacity': 0 if not app.fuckin_good_completed else 1, '_anim': False, 'active': False, 'index': 3,
                 'name': "Действие 4", 'only_start_over': False, 'stages': stages, 'only_before_pause': False,
                 'func': "poe_actions.simulacrum(action.stages)", '_timer': 30, 'have_timer': False},
                {'opacity': 0 if not app.fuckin_good_completed else 1, '_anim': False, 'active': False, 'index': 4,
                 'name': "Действие 5", 'only_start_over': False, 'stages': stages, 'only_before_pause': True,
                 'func': "poe_actions.simulacrum(action.stages)", '_timer': 45, 'have_timer': False}
            ]
        elif app.type == 'S':
            self.actions = [
                {'opacity': 0 if not app.fuckin_good_completed else 1, '_anim': False, 'active': False, 'index': 0,
                 'name': "Действие 1",
                 'func': "poe_actions.test(f'{self.index}. {self.name}')", '_timer': 0, 'have_timer': False},
            ]
        else:
            self.actions = []

        if not app.current_action:
            self.main.ids.stages_rv.data = self.actions[0]['stages']

    def set_status(self, status, append_current_action=False):
        if append_current_action:
            self.status = f"[{self.current_action.name}] {status}"
        else:
            self.status = status

    @mainthread
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
            self.main.reset_actions_completed()
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

    def start_stop(self, start):  # button callback
        if self.running == start:
            return

        if start:
            self.set_running(True, True)
            self.main.do_next_action(0)
            Snackbar(text="Запущен. Запахло наживой!!1").open()
        else:
            if self.action_thread and self.action_thread.is_alive():
                self.set_status(f"Останавливаюсь. Заканчиваю последний цикл")
                self.need_pause = True
                Snackbar(text="Буду остановлен после завершения последнего действия").open()
            else:
                self.set_running(False)
                Snackbar(text="Остановлен").open()

    def update_current_action(self, action):
        self.current_action = action
        self.action_thread = threading.Thread(target=lambda *_: eval(action.func), daemon=True)

    @mainthread
    def update_current_stage(self, index, error=""):
        if self.current_stage:
            # Меняем статус у предыдущего
            if error:
                self.current_stage.status = 'error'
                self.current_action.change_active(False)
                self.set_running(False)
                Clock.schedule_once(lambda *_: self.set_status(f"Этап: {self.current_stage.text}. Остановлен из-за ошибки:\n{error}", True))
                return
            else:
                self.current_stage.status = 'completed'

        self.current_stage = self.main.ids.stages_parent.children[-(index + 1)]
        self.current_stage.status = 'progress'

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
        self._refresh_tabs()

    def fuckin_good_start(self):
        anim = Animation(opacity=1, d=.75, transition='in_elastic')
        anim.bind(on_complete=self.fuckin_good_on_complete_anim)
        anim.start(self.ids.actions_parent.children[-1])

    def fuckin_good_on_complete_anim(self, anim, obj):
        if obj in self.ids.actions_parent.children:
            if obj != self.ids.actions_parent.children[0]:
                action = self.ids.actions_parent.children[-(obj.index + 2)]
                anim = Animation(opacity=1 if not action.only_before_pause else .5, d=.75, transition='in_elastic')
                anim.bind(on_complete=self.fuckin_good_on_complete_anim)
                anim.start(action)
            else:
                delta = self.ids.button_blacklist.parent.height - self.ids.button_blacklist.y + dp(10)
                self.ids.button_blacklist.y += delta
                self.ids.button_blacklist.opacity = 1
                anim = Animation(y=self.ids.button_blacklist.y - delta, d=1.25, transition='out_bounce')
                anim.start(self.ids.button_blacklist)

                delta = self.ids.button_queue.parent.height - self.ids.button_queue.y + dp(10)
                self.ids.button_queue.y += delta
                self.ids.button_queue.opacity = 1
                anim = Animation(y=self.ids.button_queue.y - delta, d=1.25, transition='out_bounce')
                anim.bind(on_complete=self.fuckin_good_on_complete_anim)
                Clock.schedule_once(lambda *_: anim.start(self.ids.button_queue), .65)
        elif obj == self.ids.button_queue:
            delta = self.ids.stages_box.parent.height - self.ids.stages_box.y + dp(10)
            self.ids.stages_box.y += delta
            self.ids.stages_box.opacity = 1
            anim = Animation(y=self.ids.stages_box.y - delta, d=2, transition='linear')
            anim.bind(on_complete=self.fuckin_good_on_complete_anim)
            anim.start(self.ids.stages_box)
        else:
            app.fuckin_good_completed = True
            app.start_stop(True)

    @mainthread
    def do_next_action(self, go_to=None):
        """
        Может вызываться из любого потока, но запускается в мейн.
        Логика:
        1. Запускает следующий этап текущего действия или первый этап следующего действия.
        2. Если последний - запускает первый этап первого действия.
        3. Если app.need_pause, то по завершению последнего этапа последнего действия, останавливается.
        :param start_over: Начать сначала + использовать действия, с флагом only_start_over
        :param go_to: Перейдет к действию с этим индексом. None - к следующему.
        :return:
        """

        if app.current_action:
            app.current_action.change_active(False)  # Выключаем "плей" на текущем действии
            app.current_action.reset_timer()

        actions_list = self.ids.actions_parent.children

        # Устанавливаем новое действие в текущее и запускаем его
        if not app.current_action:  # Это первый запуск
            # Элементы загружаются в обратном порядке. Последний - это первый из self.actions
            app.current_action = actions_list[-1]
        elif go_to is not None:  # Указано, к какому действию надо перейти
            app.current_action = actions_list[-(go_to + 1)]
        elif app.current_action == actions_list[0]:  # Это было последнее действие (Элементы в обратном порядке)
            if not app.need_pause:
                app.current_action = actions_list[-1]
            else:
                app.set_running(False)
                return
        else:
            # Следующий объект в списке
            app.current_action = actions_list[-(app.current_action.index + 2)]

        if not app.current_action.can_start_action():  # Если действие "погашено", тогда сразу запускаем некст
            Clock.schedule_once(lambda *_: app.main.do_next_action())
        else:  # Если всё ок, то стартуем его
            # Перезаливаем этапы, чтобы обновить статусы и прочее, что было изменено в процессе в предыдущий раз
            app.current_action.stages = app.actions[app.current_action.index]['stages']
            self.ids.stages_rv.refresh_from_data()
            app.current_action.play_pause(True)

        if app.current_action == actions_list[0]:  # Если последнее действие, сбиваем флаг
            app.start_over = False

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

    def reset_actions_completed(self):
        # map(ActionBox.reset_completed, self.ids.actions_parent.children)
        for action in self.ids.actions_parent.children:
            action.completed = False

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

    def fill_logs(self):
        self.ids.logs_box.data = [{
            'text': "Тестовый текст лога " + str(x),
            'character': "snckmykek_q_test123",
            'trade_id': "ADkjN28OI2ni4",
            'level': x % 4 if x % 4 != 0 else 1,
            'item': "Foreboding Delirium Orb",
            'datetime': datetime.now().strftime("%b %d %H:%M:%S"),
        } for x in range(10000)]

    def _refresh_tabs(self):
        pass
        # self.refresh_items()
        # self.refresh_logs()
        # self.refresh_settings()


class ActionBox(MDCard, RoundedRectangularElevationBehavior):
    _anim_elevation = None
    _anim_timer = None
    _min_opacity = NumericProperty(.3)
    _max_opacity = NumericProperty(1)
    _timer = NumericProperty(0)
    completed = BooleanProperty(False)
    active = BooleanProperty(False)
    func = StringProperty("")
    have_timer = BooleanProperty(False)
    index = NumericProperty(0)
    name = StringProperty("")
    only_before_pause = BooleanProperty(False)
    only_start_over = BooleanProperty(False)
    stages = ListProperty([])
    timer = NumericProperty(0)

    def __init__(self, **kwargs):
        super(ActionBox, self).__init__(**kwargs)
        self._anim_timer = Animation(_timer=0, duration=self._timer)
        Clock.schedule_once(lambda *_: self.reset_timer())

    def play_pause(self, is_active=True):
        if is_active and not self.can_start_action():
            return

        if is_active and app.action_thread and app.action_thread.is_alive():
            Snackbar(text="Для запуска действия, нужно остановить все остальные").open()
            return

        self.change_active(is_active)
        if is_active:
            app.need_stop_action = False
            app.set_running(True, self.index == 0)
            self.go_action()
        else:
            app.need_stop_action = True

    def can_start_action(self):
        return not ((self.only_before_pause and not app.need_pause)
                    or (self.only_start_over and (self.completed or not app.start_over)))

    def change_active(self, value):
        self.active = value
        self._change_elevation()
        if self.active:
            self.reset_timer()
            self._anim_timer = Animation(timer=0, duration=self.timer)
            self._anim_timer.bind(on_complete=self.timeout)
            self._anim_timer.start(self)
        else:
            self.completed = True
            self._anim_timer.cancel(self)

    def go_action(self):
        app.update_current_action(self)
        app.action_thread.start()

    def reset_completed(self):
        self.completed = False

    def timeout(self, *args):
        if not self.active:
            return

        self.change_active(False)
        app.need_stop_action = True

    def reset_timer(self):
        self.timer = self._timer

    def _change_elevation(self):
        if self._anim_elevation:
            self._anim_elevation.cancel(self)
        self._anim_elevation = Animation(elevation=0 if self.active else dp(12), d=0.08)
        self._anim_elevation.start(self)


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


app: ControlPanelApp
if __name__ == "__main__":
    ControlPanelApp().run()
    app = MDApp.get_running_app()
