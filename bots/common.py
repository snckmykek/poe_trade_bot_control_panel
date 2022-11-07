import os
from os.path import dirname

from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivymd.uix.dialog import MDDialog
from kivymd.uix.textfield import MDTextField

Builder.load_file(os.path.join(dirname(__file__), 'common.kv'))


class CustomDialog(MDDialog):

    def update_width(self, *args) -> None:
        if self.content_cls.size_hint_x is None:
            self.width = self.content_cls.width + dp(36)
        else:
            super(CustomDialog, self).update_width(*args)

    def on_pre_open(self):
        super(CustomDialog, self).on_open()
        self.update_width()


class CustomMDTextField(MDTextField):
    helper_texts = {
        'int': "Только целые числа",
        'float': "Только числа",
        'str': ""
    }
    text_type = StringProperty("str", options=helper_texts.keys())

    def check_mask_text(self, instance, value):
        self.error = not text_is_correct(self.text_type, value)


def text_is_correct(text_type, value):
    if text_type == 'str' or not value:
        return True
    elif text_type == 'int':
        try:
            int(value)
            return True
        except ValueError:
            return False
    elif text_type == 'float':
        try:
            float(value)
            return True
        except ValueError:
            return False
