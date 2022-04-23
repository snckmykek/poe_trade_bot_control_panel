from kivy.config import Config

Config.set('graphics', 'resizable', '1')
Config.set('graphics', 'width', '1000')
Config.set('graphics', 'height', '640')

from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.clock import Clock
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout

import glob
glob.upload_config()


class ControlPanelApp(MDApp):
    status = StringProperty("Не запущен")
    stopped = BooleanProperty(True)

    def __init__(self, **kwargs):
        super(ControlPanelApp, self).__init__(**kwargs)
        Clock.schedule_interval(lambda *_: self.update_data(), 1)

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Teal"
        return MainScreen()

    def set_stopped(self, stopped):
        self.stopped = stopped

        if self.stopped:
            self.set_status("Остановлен вручную")
        else:
            self.set_status("Начинаю работу")

    def set_status(self, status):
        self.status = status

    def update_data(self):
        # stopped, status?
        pass


class MainScreen(MDBoxLayout):
    test_text = StringProperty("")

    def __init__(self, **kwargs):
        super(MainScreen, self).__init__(**kwargs)

    def refresh_items(self):
        self.ids.items_list.clear_widgets()
        for i in range(20):
            self.ids.items_list.add_widget(ItemBox(name=f"item test {i}"))

    def set_use_all_items(self, value):
        for item in self.ids.items_list.children:
            item.use = value


class ItemBox(MDBoxLayout):
    use = BooleanProperty(False)
    name = StringProperty("Name")
    max_price = NumericProperty(0)
    bulk_price = NumericProperty(0)
    qty = NumericProperty(0)

    def __init__(self, **kwargs):
        super(ItemBox, self).__init__(**kwargs)


if __name__ == "__main__":
    ControlPanelApp().run()
