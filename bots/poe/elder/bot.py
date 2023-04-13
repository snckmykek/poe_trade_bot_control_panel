import json
import time

import cv2
import keyboard
import numpy as np
import pyautogui
from matplotlib import pyplot as plt

from bots.poe.poe_base import PoeBase
from bots.bot import Simple, Template, Coord
from common import abs_path_near_exe


class PoeElder(PoeBase):
    # Обязательные
    icon = 'sword'
    name = "ПОЕ: Елдер"
    key = "poe_elder"

    # Кастомные
    qty = 0
    items = {}

    def __init__(self):
        super(PoeElder, self).__init__()

        self.set_task_tab_buttons()
        self.set_tasks()
        self.set_windows()

    # region init
    def set_task_tab_buttons(self):
        self.task_tab_buttons = [
        ]

    def set_tasks(self):
        self.tasks = [
            {
                'name': "Вход",
                'timer': 60,
                'available_mode': 'after_start',
                'stages': [
                    {
                        'func': self.start_poe,
                        'name': "Запуск ПОЕ по ярлыку"
                    },
                    {
                        'func': self.authorization,
                        'name': "Авторизация"
                    },
                    {
                        'func': self.choice_character,
                        'name': "Выбор перса"
                    },
                ]
            },
            {
                'name': "Действия перед стартом",
                'timer': 10,
                'available_mode': 'after_start',
                'stages': [
                    {
                        'func': self.stub,
                        'name': "Установить дату старта сессии"
                    },
                ]
            },
            {
                'name': "Фармить",
                'timer': 300,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.activate_map,
                        'name': "Активировать мапу (при необходимости, взять валюту)"
                    },
                    {
                        'func': self.go_to_farm_loc,
                        'name': "Зайти к боссу/на мапу"
                    },
                    {
                        'func': self.farming_loc,
                        'name': "Зачистить босса/мапу"
                    },
                    {
                        'func': self.take_loot,
                        'name': "Собрать лут"
                    },
                    {
                        'func': self.go_to_hideout,
                        'name': "Вернуться в ХО"
                    },
                ]
            },
            {
                'name': "Выход из ПОЕ на перерыв",
                'timer': 10,
                'available_mode': 'before_break',
                'stages': [
                    {
                        'func': self.close_poe,
                        'name': "Выход alt+f4"
                    }
                ]
            },
        ]

    def set_variables_setting(self):
        self.variables_setting = {
            'Общие настройки': [
                Simple(
                    key='test',
                    name="Тест",
                    type='str'
                ),
            ],
            'Окно: Path of Exile (игра)': [
                Coord(
                    key='coord_currency_tab',
                    name="Координаты валютной вкладки",
                    relative=True,
                    type='coord',
                    window='poe'
                ),
                Template(
                    key='template_game_loaded',
                    name="Статичный кусок экрана, однозначно говорящий о загрузке локи "
                         "(например, сиськи телки где мана)",
                    region=Coord(
                        key='region_game_loaded',
                        name="",
                        relative=True,
                        snap_mode='rb',
                        type='region',
                        window='poe'
                    ),
                    relative=True,
                    type='template',
                    window='poe'
                ),
            ]
        }

    def set_windows(self):
        self.windows = {
            'main': {'name': ""},
            'poe': {'name': "Path of Exile", 'expression': ('x', 'y', 'w', 'h')},
            'poe_except_inventory': {'name': "Path of Exile", 'expression': ('x', 'y', 'w - 0.6166 * h', 'h')}

        }

    def delayed_init(self, *_):
        self.set_variables_setting()

    # endregion

    def activate_map(self):
        self.open_map_device()
        if not self.check_fragments():
            self.clear_invent_and_restock_fragments_in_map_device()
        self.click_to_activate_map()

    def go_to_farm_loc(self):
        self.go_portal_to_map()
        self.go_portal_to_boss()

    def farming_loc(self):
        self.go_to_center_and_setup_mines()
        self.go_behind_boss()
        self.throw_mines_to_center_from_behind_boss()
        self.go_to_safe_zone()
        self.throw_mines_to_center_from_safe_zone()

    def go_to_hideout(self):
        self.go_portal_to_intermediate()
        self.go_portal_to_glacial_hideout()

        self.qty = self.qty + 1
        self.save_stat()

    def open_map_device(self):
        coord = self.find_template('map_device')
        if not coord:
            self.click_to_template_with_condition('stash', 'stash_header')
            keyboard.press_and_release('esc')
        self.click_to_template_with_condition('map_device', 'map_device_header')

    def check_fragments(self):
        coord = self.find_template('fragments', accuracy=.95)
        return coord is not None

    def clear_invent_and_restock_fragments_in_map_device(self):
        keyboard.press_and_release('esc')

        self.click_to_template_with_condition('stash', 'stash_header')

        self.clear_inventory()

        self.mouse_move_and_click(546, 115, duration=.15, sleep_after=.2)
        self.mouse_move_and_click(449, 153, duration=.15, sleep_after=.2)
        self.mouse_move_and_click(92, 192, duration=.15, sleep_after=.2)

        self.key_down('ctrl', sleep_after=.2)
        self.mouse_move_and_click(123, 660, duration=.15, sleep_after=.2)
        self.mouse_move_and_click(126, 720, duration=.15, sleep_after=.2)
        self.mouse_move_and_click(190, 660, duration=.15, sleep_after=.2)
        self.mouse_move_and_click(186, 716, duration=.15, sleep_after=.2)
        self.key_up('ctrl', sleep_after=.2)

        keyboard.press_and_release('esc')
        time.sleep(.2)

        self.click_to_template_with_condition('map_device', 'map_device_header')

        self.clear_inventory()

    def click_to_activate_map(self):
        self.click_to_template_with_condition('activate', 'map_device')

    def go_portal_to_map(self):
        self.click_to_template_with_condition('portal_to_map', 'glacial_hideout')

    def go_portal_to_boss(self):
        self.mouse_move_and_click(880, 1000)
        time.sleep(1)
        self.click_to_template_with_condition('portal_to_boss', 'portal_to_map')

    def go_to_center_and_setup_mines(self):
        self.mouse_move_and_click(604, 244)
        time.sleep(1.5)

        pyautogui.moveTo(684, 240)
        keyboard.press(18)
        time.sleep(3)

        keyboard.release(18)
        time.sleep(.15)

        keyboard.press_and_release(20)
        time.sleep(.15)

    def go_behind_boss(self):
        self.mouse_move_and_click(620, 161)
        time.sleep(2)

    def throw_mines_to_center_from_behind_boss(self):
        self.mouse_move(1350, 824, duration=.1)
        keyboard.press([16, 18])
        time.sleep(10)
        keyboard.release([16, 18])

    def go_to_safe_zone(self):
        pyautogui.click()
        time.sleep(1)
        self.mouse_move_and_click(1486, 886)
        time.sleep(1)

    def throw_mines_to_center_from_safe_zone(self):
        self.mouse_move(587, 248, duration=.1)
        keyboard.press([16, 18])
        time.sleep(85)
        keyboard.release([16, 18])

    def take_loot(self):
        self.mouse_move_and_click(1030, 184, duration=.15, sleep_after=.15)
        time.sleep(1)
        loot_list = ['prismatic_jewel', 'fragment_of_terror', 'fragment_of_emptiness', 'orb_of_dominance', 'the_feared']

        for loot in loot_list:
            self.pick_up_item(loot)

        self.mouse_move_and_click(1322, 429, duration=.15, sleep_after=.15)

        for loot in loot_list:
            self.pick_up_item(loot)

    def go_portal_to_intermediate(self):
        self.mouse_move_and_click(1530, 860)
        time.sleep(1)
        self.click_to_template_with_condition('portal_to_map', 'portal_to_boss')
        self.mouse_move_and_click(820, 3)
        time.sleep(1.5)

    def go_portal_to_glacial_hideout(self):
        self.click_to_template_with_condition('glacial_hideout', 'stash')

    def pick_up_item(self, template_name):
        self.click_to(template_name, wait_template=False, accuracy=.6)

        try:
            self.items[template_name] += 1
        except KeyError:
            self.items.update({template_name: 1})

    def upload_stat(self):
        try:
            with open('stat.json', 'r', encoding='utf-8') as f:
                self.items = json.load(f)
        except FileNotFoundError:
            pass

    def save_stat(self):
        with open('stat.json', 'w', encoding='utf-8') as f:
            json.dump(self.items, f)
            

def find_template(template_name, accuracy=.85):
    template = (plt.imread(abs_path_near_exe(f"images/templates/poe_elder/{template_name}.png")) * 255).astype(np.uint8)
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

    pyautogui.moveTo(1, 1)
    screenshot = pyautogui.screenshot()
    img_rgb = np.array(screenshot)
    img_gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)

    result = cv2.matchTemplate(img_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    if result.max() > accuracy:
        coord = cv2.minMaxLoc(result)[-1]
        # cv2.rectangle(img_rgb, coord, [coord[0] + template.shape[1], coord[1] + template.shape[0]], [255]*3)
        # cv2.imshow("Image", img_rgb)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()
        return coord
    else:
        return None
