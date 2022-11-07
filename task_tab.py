import os
from os.path import dirname

from kivy.animation import Animation
from kivy.clock import Clock, mainthread
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty, OptionProperty, \
    ObjectProperty
from kivy.uix.behaviors import ButtonBehavior
from kivymd.app import MDApp
from kivymd.uix.behaviors import RoundedRectangularElevationBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.list import OneLineIconListItem
from kivymd.uix.snackbar import Snackbar

app = MDApp.get_running_app()
Builder.load_file(os.path.join(dirname(__file__), "task_tab.kv"))


class TaskTab(MDBoxLayout):

    def __init__(self, **kwargs):
        global app
        app = MDApp.get_running_app()
        super(TaskTab, self).__init__(**kwargs)

    def first_run_animation_start(self):
        anim = Animation(opacity=1, d=.75, transition='in_elastic')
        anim.bind(on_complete=self.first_run_animation_on_complete_anim)
        anim.start(self.ids.actions_parent.children[-1])

    def first_run_animation_on_complete_anim(self, anim, obj):
        if obj in self.ids.actions_parent.children:
            if obj != self.ids.actions_parent.children[0]:
                action = self.ids.actions_parent.children[-(obj.index + 2)]
                anim = Animation(opacity=1 if not action.only_before_pause else .5, d=.75, transition='in_elastic')
                anim.bind(on_complete=self.first_run_animation_on_complete_anim)
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
                anim.bind(on_complete=self.first_run_animation_on_complete_anim)
                Clock.schedule_once(lambda *_: anim.start(self.ids.button_queue), .65)
        elif obj == self.ids.button_queue:
            delta = self.ids.stages_box.parent.height - self.ids.stages_box.y + dp(10)
            self.ids.stages_box.y += delta
            self.ids.stages_box.opacity = 1
            anim = Animation(y=self.ids.stages_box.y - delta, d=2, transition='linear')
            anim.bind(on_complete=self.first_run_animation_on_complete_anim)
            anim.start(self.ids.stages_box)
        else:
            app.main.first_run_animation_after()


class TaskBox(MDCard, RoundedRectangularElevationBehavior, ButtonBehavior):
    _anim_timer = None
    _max_opacity = NumericProperty(1)
    _min_opacity = NumericProperty(.3)
    active = BooleanProperty(False)
    available_mode = StringProperty('always', options=['always', 'after_start', 'before_break'])
    completed_once = BooleanProperty(False)
    extended = BooleanProperty(False)
    index = NumericProperty(0)
    name = StringProperty("")
    stages = ListProperty([])
    timer = NumericProperty(0)
    task_time = NumericProperty(0)

    def __init__(self, **kwargs):
        super(TaskBox, self).__init__(**kwargs)
        if self.task_time:
            Clock.schedule_once(lambda *_: self.reset_timer())

    def available(self):
        return (
                self.available_mode == 'always'
                or (self.available_mode == 'before_break' and app.need_break)
                or (self.available_mode == 'after_start' and not self.completed_once)
        )

    def on_timeout(self, *args):
        if not self.active:
            return

        app.need_stop_task = True

    def play_callback(self, is_active=True):
        if is_active and not self.available():
            Snackbar(text="Действие доступно только при старте или перед паузой").open()
            return

        if is_active and app.tasks_obj[app.current_task].active:
            Snackbar(text="Для запуска действия нужно остановить текущее").open()
            return

        if is_active:
            app.start_by_task((self.index, 0))
        else:
            app.need_stop_task = True

    def reset_timer(self):
        self.timer = self.task_time

    def start(self):
        if not self.extended:
            app.display_stages(self.index)
        self.active = True
        self._change_elevation()
        self.start_timer()

    def start_timer(self):
        if self.task_time:
            self.stop_timer()

            self.reset_timer()
            self._anim_timer = Animation(timer=0, duration=self.timer)
            self._anim_timer.bind(on_complete=self.on_timeout)
            self._anim_timer.start(self)

    def stop(self):
        self.active = False
        self.completed_once = True
        self.stop_timer()

    def stop_timer(self):
        if self._anim_timer:
            self._anim_timer.cancel(self)

    def _change_elevation(self):
        Animation(elevation=0 if self.active else dp(12), d=0.08).start(self)


class Stage(OneLineIconListItem):
    index = NumericProperty(0)
    widgets = {
        'queue': 'sleep',
        'progress': 'play-circle-outline',
        'completed': 'check',
        'error': 'close-circle',
        'stopped': 'pause-octagon-outline'
    }

    def start(self):
        # Проверяем доступность новой задачи
        if not app.tasks_obj[app.extended_task].available():
            Snackbar(text="Действие доступно только при старте или перед паузой").open()
            return

        # При активной задаче нельзя запустить другой этап
        if app.tasks_obj[app.current_task].active:
            Snackbar(text="Для запуска действия нужно остановить текущее").open()
            return

        app.start_by_task([app.extended_task, self.index])


class Stages(MDCard):
    current_status = OptionProperty('queue', options=['progress', 'error', 'stopped'])

    def set_current_status(self, status):
        self.current_status = status

    def calculate_height(self):
        return len(self.ids.stages_rv.data) * (self.ids.stages_parent.default_size[1] + self.ids.stages_parent.spacing)\
               + 1
