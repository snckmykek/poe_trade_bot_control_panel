import datetime
import random
import time

from kivy.metrics import dp
from kivymd.uix.button import MDRectangleFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.snackbar import Snackbar

from bots.bot import Bot, Coord, Simple, Template


class ExampleBot(Bot):
    """Описание настроек см. bots/bot"""

    # region Обязательные параметры для любого бота
    icon = 'presentation-play'
    name = "Example bot"
    key = "example"
    # endregion

    """
    Кастомные служебные переменные. Задаются и используются только внутри бота
    """
    service_variables = {
        'test': "Тестовый контент",
        'test_list': ["Строка 1", "Строка 2", "Строка 3"]
    }

    def __init__(self):
        super(ExampleBot, self).__init__()

        self.task_tab_buttons = [
            {
                'text': "Открыть диалоговое окно",
                'icon': 'alert-box-outline',
                'func': self.open_dialog_window
            },
            {
                'text': "Написать оповещалку",
                'icon': 'information-outline',
                'func': self.notify
            },
        ]

        self.task_tab_content = MDGridLayout(
            cols=1,
            padding=[dp(20), dp(20)]
        )

        self.task_tab_content.add_widget(
            MDLabel(
                text=self.service_variables['test'],
                size_hint=[1, 1]
            )
        )

        for line in self.service_variables['test_list']:
            self.task_tab_content.add_widget(
                MDLabel(
                    text=line,
                    size_hint=[1, 1]
                )
            )

        self.tasks = [
            {'name': "Приветствие",
             'timer': 5,
             'available_mode': 'after_start',
             'stages': [
                 {
                     'func': self.task0_stage0,
                     'name': "Сказать Привет"
                 },
             ]
             },
            {'name': "Посчитать до 5",
             'timer': 10,
             'available_mode': 'always',
             'stages': [
                 {
                     'func': self.task1_stage0,
                     'name': "1"
                 },
                 {
                     'func': self.task1_stage1,
                     'name': "2"
                 },
                 {
                     'func': self.task1_stage2,
                     'name': "3"
                 },
                 {
                     'func': self.task1_stage3,
                     'on_error': {'goto': (1, 0)},
                     'name': "4"
                 },
                 {
                     'func': self.task1_stage4,
                     'name': "5"
                 },
             ]
             },
            {'name': "Прощание",
             'timer': 5,
             'available_mode': 'before_break',
             'stages': [
                 {
                     'func': self.task2_stage0,
                     'name': "Сказать Пока"
                 }
             ]
             },
        ]

        self.variables_setting = {
            'Данные аккаунта': [
                Simple(
                    key='login',
                    name='Логин',
                    type='str'
                ),
                Simple(
                    key='password',
                    name="Пароль",
                    type='str'
                )],
            'Основные': [
                Simple(
                    key='start_delay',
                    name="Задержка перед стартом",
                    type='int'
                ),
                Simple(
                    key='test_param',
                    name="Тестовый параметр",
                    type='str'
                )],
            'Окно: раб. стол': [
                Coord(
                    key='desktop_coord_of_smth',
                    name="Координаты чего-нибудь на раб столе",
                    relative=True,
                    snap_mode='lt',
                    type='coord'
                )],
            'Окно: Example app': [
                Coord(
                    key='login_button_coord',
                    name="Координаты кнопки Войти",
                    relative=True,
                    snap_mode='lt',
                    type='coord'
                ),
                Coord(
                    key='buttons_coord',
                    name="Список координат кнопок, для нажатия в цикле",
                    relative=False,
                    snap_mode='lt',
                    type='coord_list'
                ),
                Coord(
                    key='inventory_region',
                    name="Область ячеек инвентаря",
                    relative=False,
                    snap_mode='rb',
                    type='region'
                ),
                Template(
                    key='template_find_on_window',
                    name="Шаблон, для его поиска в окне",
                    region=Coord(
                        key='region_find_on_window',
                        name="",
                        relative=True,
                        snap_mode='rb',
                        type='region',
                        window='main_screen'
                    ),
                    relative=True,
                    type='template',
                    window='main_screen'
                ),
                Template(
                    key='template_find_inside_region',
                    name="Шаблон, для его поиска в области",
                    region=Coord(
                        key='region_find_inside_region',
                        name="",
                        relative=False,
                        snap_mode='lt',
                        type='region',
                        window='example_bot'
                    ),
                    relative=False,
                    type='template',
                    window='example_bot'
                )]
        }

        self.windows = {
            'main_screen': "",
            'example_bot': "ControlPanel"
        }

    @staticmethod
    def open_dialog_window(_button):
        dialog = MDDialog(
            auto_dismiss=False,
            text="Эта кнопка открывает диалоговое окно",
            buttons=[
                MDRectangleFlatButton(
                    text="OK"
                ),
            ],
        )
        dialog.buttons[0].bind(on_release=dialog.dismiss)
        dialog.open()

    @staticmethod
    def notify(_button):
        Snackbar(text="Эта кнопка вызывает оповещение").open()

    @staticmethod
    def task0_stage0():
        time.sleep(2)

    @staticmethod
    def task1_stage0():
        time.sleep(1)

    @staticmethod
    def task1_stage1():
        time.sleep(1)

    @staticmethod
    def task1_stage2():
        time.sleep(1)

    def task1_stage3(self):
        if random.choice([True, False]):
            self.log.update({
                'date': int(datetime.datetime.now().timestamp()),
                'details': "Забыл, сколько после цифры 3",
                'level': 1,
                'text': "Забыл, сколько дальше"
            })
            return "Забыл, сколько дальше"
        time.sleep(1)

    @staticmethod
    def task1_stage4():
        time.sleep(1)

    @staticmethod
    def task2_stage0():
        time.sleep(2)
