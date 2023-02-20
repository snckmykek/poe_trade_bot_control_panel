import time

import cv2
import pyautogui
import numpy as np
from kivy.properties import NumericProperty
from kivymd.app import MDApp
from kivy.clock import Clock

from bots.bot import Bot, Coord
from bots.poe.craft.additional_functional import Content1 as Content

app = MDApp.get_running_app()


class PoeCraft(Bot):
    # Обязательные
    icon = 'account-arrow-left'
    name = "ПОЕ: Craft"
    key = "poe_craft"

    # Кастомные
    qty = NumericProperty()
    last_qty = NumericProperty()

    def __init__(self):
        super(PoeCraft, self).__init__()

        self.set_task_tab_buttons()
        self.set_tasks()
        self.set_variables_setting()
        self.set_windows()

        Clock.schedule_once(self.delayed_init)

    def delayed_init(self, *_):
        self.task_tab_content = Content()
        self.app.add_task_content()

    def set_task_tab_buttons(self):
        self.task_tab_buttons = [
        ]

    def set_tasks(self):
        self.tasks = [
            {
                'name': "Искать мод",
                'timer': 3600,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.reset,
                        'name': "Сбросить начальные данные"
                    },
                    {
                        'func': self.wait_start,
                        'name': "Ждать f11 для старта",
                        'on_error': {'goto': (0, 2)}
                    },
                    {
                        'func': self.click_while_mode,
                        'name': "Кликать пока не будет мод"
                    },
                ]
            },
        ]

    def set_variables_setting(self):
        self.variables_setting = {
            'Окно: Path of Exile': [
                Coord(
                    key='coord_alt',
                    name="Координаты альтов",
                    relative=True,
                    snap_mode='lt',
                    type='coord',
                    window='poe'
                ),
                Coord(
                    key='coord_item',
                    name="Координаты итема",
                    relative=True,
                    snap_mode='lt',
                    type='coord',
                    window='poe'
                ),
                Coord(
                    key='region_frame',
                    name="Координаты участка рамки, который станет зеленым",
                    relative=True,
                    snap_mode='lt',
                    type='region',
                    window='poe'
                ),
            ]
        }

    def set_windows(self):
        self.windows = {
            'main': {'name': ""},
            'poe': {'name': "Path of Exile", 'expression': ('x', 'y', 'w', 'h')}
        }

    def reset(self):
        self.last_qty = 0

    def wait_start(self):
        while not self.stop():
            time.sleep(.1)

        raise TimeoutError("Запущен")

    def click_while_mode(self):
        pyautogui.keyDown('shift')

        self.move_alt_to_item()

        # Первый раз клик в любом случае
        pyautogui.click()
        time.sleep(.1)

        region_frame = self.v('region_frame')
        while not self.check_mode(region_frame):
            self.check_freeze()

            pyautogui.click()

            if self.stop():
                raise TimeoutError("Завершено по времени или вручную")

            self.qty += 1
            self.last_qty += 1
        pyautogui.keyUp('shift')

    def move_alt_to_item(self):
        self.mouse_move(self.v('coord_alt'))
        pyautogui.click(button='right')
        self.mouse_move(self.v('coord_item'))

    @staticmethod
    def check_mode(region_frame):
        time.sleep(.05)
        img = np.array(pyautogui.screenshot(region=region_frame))
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return len(np.where(img_gray > 150)[0]) > 0
