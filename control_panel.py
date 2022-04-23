from kivy.config import Config

Config.set('graphics', 'resizable', '1')
Config.set('graphics', 'width', '1000')
Config.set('graphics', 'height', '640')

from kivy.properties import StringProperty, BooleanProperty
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout


class ControlPanelApp(MDApp):
    def __init__(self, **kwargs):
        super(ControlPanelApp, self).__init__(**kwargs)

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Teal"
        return MainScreen()


class MainScreen(MDBoxLayout):
    def __init__(self, **kwargs):
        super(MainScreen, self).__init__(**kwargs)


if __name__ == "__main__":
    ControlPanelApp().run()