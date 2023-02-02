import os
from kivy.lang import Builder

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout

app = MDApp.get_running_app()
Builder.load_file(os.path.abspath(os.path.join(os.path.dirname(__file__), "additional_functional.kv")))


class Content1(MDBoxLayout):
    pass


