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

app = MDApp.get_running_app()
Builder.load_file("action_tab.kv")


class ActionTab(MDBoxLayout):

    def __init__(self, **kwargs):
        global app
        app = MDApp.get_running_app()
        super(ActionTab, self).__init__(**kwargs)

    @mainthread
    def do_next_action(self, go_to=None):
        """
        Может вызываться из любого потока, но запускается в мейн.
        Логика:
        1. Запускает следующий этап текущего действия или первый этап следующего действия.
        2. Если последний - запускает первый этап первого действия.
        3. Если app.need_pause, то по завершению последнего этапа последнего действия, останавливается.
        :param go_to: Перейдет к действию с этим индексом. None - к следующему.
        :return:
        """

        if app.current_action:
            app.current_action.change_active(False)  # Выключаем "плей" на текущем действии
            app.current_action.reset_timer()

        next_action = self.get_next_action(go_to)
        if not next_action:
            app.set_running(False)
            return

        app.update_current_action(next_action)
        app.current_action.stages = app.actions[app.type][app.current_action.index]['stages']
        self.ids.stages_rv.refresh_from_data()
        app.current_action.play_pause(True)

    def go_action(self, action):
        app.need_stop_action = False
        self.set_actions_completed(action.index)
        app.set_running(True)
        app.update_current_action(action)
        app.action_thread.start()

    def get_next_action(self, go_to):

        actions_list = self.ids.actions_parent.children
        if not app.current_action:  # Нет текущего, тогда следующий - первый
            # Элементы загружаются в обратном порядке. Последний - это первый из self.actions
            next_action = actions_list[-1]
        elif go_to is not None:  # Указано, к какому действию надо перейти
            next_action = actions_list[-(go_to + 1)]
        elif self.is_last_available_action(app.current_action.index):  # Это было последнее доступное действие
            self.reset_actions_completed()
            if not app.need_pause:
                # Берем не просто первый, а первый доступный элемент
                next_action = None
                for action in actions_list:
                    if action.available():
                        next_action = action
            else:
                next_action = None
        else:  # Следующий объект в списке
            next_action = actions_list[-(app.current_action.index + 2)]

        return next_action

    def is_last_available_action(self, index):
        actions_list = self.ids.actions_parent.children

        for action in actions_list:
            if action.index > index and action.available():
                return False

        return True

    def fill_default_stages(self):
        self.ids.stages_rv.data = app.actions[app.type][0]['stages']

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

    def report_current_stage(self, index, error=""):
        if app.current_stage:  # Меняем статус у предыдущего
            if error:
                app.current_stage.status = 'error'
                app.current_action.change_active(False)
                app.set_running(False)
                Clock.schedule_once(lambda *_: app.set_status(
                    f"Этап: {app.current_stage.text}. Остановлен из-за ошибки:\n{error}", True))
                return
            else:
                app.current_stage.status = 'completed'

        current_stage = self.ids.stages_parent.children[-(index + 1)]
        current_stage.status = 'progress'

        app.update_current_stage(current_stage)
        app.set_status(f"Выполняю.", True, True)

    def reset_actions_completed(self, _all=False):
        for action in self.ids.actions_parent.children:
            if _all or not action.only_start_over:
                action.completed = False

    def set_actions_completed(self, _index=0):
        for action in self.ids.actions_parent.children:
            if action.index < _index:
                action.completed = True


class ActionBox(MDCard, RoundedRectangularElevationBehavior):
    _anim_elevation = None
    _anim_timer = None
    _min_opacity = NumericProperty(.3)
    _max_opacity = NumericProperty(1)
    _timer = NumericProperty(0)
    completed = BooleanProperty(False)
    active = BooleanProperty(False)
    func_timer_over = ObjectProperty()
    have_timer = BooleanProperty(False)
    index = NumericProperty(0)
    name = StringProperty("")
    only_before_pause = BooleanProperty(False)
    only_start_over = BooleanProperty(False)
    stages = ListProperty([])
    timer = NumericProperty(0)

    def __init__(self, **kwargs):
        super(ActionBox, self).__init__(**kwargs)
        if self.have_timer:
            self._anim_timer = Animation(_timer=0, duration=self._timer)
            self.func_timer_over = lambda *_: app.do_next_action()
            Clock.schedule_once(lambda *_: self.reset_timer())

    def play_pause(self, is_active=True):
        if is_active and not self.available():
            return

        if is_active and app.action_thread and app.action_thread.is_alive():
            Snackbar(text="Для запуска действия, нужно остановить все остальные").open()
            return

        self.change_active(is_active)
        if is_active:
            app.main.ids.action_tab.go_action(self)
        else:
            app.need_stop_action = True

    def available(self):
        return not ((self.only_before_pause and not app.need_pause)
                    or (self.only_start_over and self.completed))

    def change_active(self, value):
        self.active = value
        self._change_elevation()
        if self.active:

            if self.have_timer:
                self.reset_timer()

                self._anim_timer = Animation(timer=0, duration=self.timer)
                self._anim_timer.bind(on_complete=self.timeout)
                self._anim_timer.start(self)
        else:
            self.completed = True
            if self.have_timer:
                self._anim_timer.cancel(self)

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