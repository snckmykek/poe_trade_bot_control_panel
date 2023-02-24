import traceback
from datetime import datetime
import os
from dataclasses import dataclass
from typing import Literal

from imutils.object_detection import non_max_suppression
from kivy.event import EventDispatcher
from kivy.properties import DictProperty
from kivy.uix.widget import Widget
from kivymd.app import MDApp

from ctypes.wintypes import HWND, DWORD, RECT
import ctypes
import cv2
import numpy as np
import pyautogui
import requests
import matplotlib.pyplot as plt
import pywintypes
import time
import win32gui
from win32api import GetSystemMetrics

from common import resource_path
from controllers import mouse_controller
from errors import StopStepError

dwmapi = ctypes.WinDLL("dwmapi")
pyautogui.FAILSAFE = False  # Прекращает работу при наведении в левый верхний угол (если надо прекратить ошибочный код)
pyautogui.PAUSE = 0  # Задержка после каждого действия. В проекте предусмотрены свои задержки


class Bot(EventDispatcher):
    """"""

    """
    Очередь на контроль мышкой и клавиатурой. 
    Перед любым действием с дивайсами, функция должна ставать в очередь на получение контроля. Если кроме нее нет 
    никого, кто пользуется девайсами, она получает контроль, иначе ждет.
    После использования девайсов, нужно отпустить контроль.
    
    Пример использования:
    self.take_control('func_1')
    some_actions_with_mouse() 
    self.release_control('func_1')
    """
    _control_queue = []

    """Ссылка на объект приложения"""
    app = MDApp.get_running_app()

    """
    Иконка бота, отображается в шапке.
    Может быть как из списка kivymd.icon_definitions.md_icons, так и путь до картинки 48*48
    Обязательно задается до инициализации
    """
    icon: str = 'presentation-play'

    """Любой словарь для удобства хранения логов в процессе выполнения этапа (после - сохраняется в БД и обнуляется)"""
    log: dict = {}

    """
    Имя бота. 
    Используется в статусе, при создании папок с шаблонами и сохранении в БД. 
    Обязательно задается до инициализации
    """
    name: str = "Example bot"

    """Ключ бота. Используется для пути до папки с шаблонами 'images/templates/{key}', имени БД '{key}.bd' и прочее"""
    key: str = "bot"

    """Если флаг взведен, то обновляет кэшированные значения у объектов из _variables"""
    need_update_cached_variables_values: bool = True

    """
    Список задач и этапов в формате:
    [
    {'name': 'Поприветствовать' (Название задачи),
     'timer': 5 (Время в секундах на все входящие этапы, при окончании - выход из задачи),
     'only_start_over': True/False (такие задачи выполняются только один раз после выхода из перерыва. Например,
                                    вход в игру и лог ин после перерыва),
     'only_before_pause': True/False (такие задачи выполняются только один перед паузой. Например,
                                      выход из игры перед перерывом),
     'stages': [
         {
             'func': self.task0_stage0 (выполняемая функция),
             'text': 'Приветствие' (Название этапа),
             'on_error': {'goto': 1, 'func': self.smth_when_error} (Словарь, дополняет словарь результата при ошибке.
                Оба ключа необязательные. Если есть функция, она будет выполняться в главном потоке)
         },
         ...
     ]
     },
     ...
     ]
    """
    tasks: list = []

    """
    Кнопки для дополнительных команд.
    Размещаются на вкладке 'задачи' в правой нижней части.
    """
    task_tab_buttons: list = []

    """
    Любой Kivy объект, который можно разместить в BoxLayout.
    Размещаются на вкладке 'задачи' в правой верхней части.
    """
    task_tab_content: Widget = None

    """
    Переменные. Шаблоны и другие данные, настраиваются пользователем.
    Словарь {Переменная: Значение, ...}
    Типы значений:
        - 'text': Любая инфа, хранится в виде строки 
            Значение - строка. Приводить к нужному типу данных следует в процессе использования значения
        - 'coord': Список из 2 значений [x, y]
            Значение - словарь вида {'relative': True/False, 'value': [int(x), int(y)]}
        - 'coord_list': Список списков из 2 значений [[x1, y1],..., [xn, yn]]
            Значение - словарь вида {'relative': True/False, 'value': [[int(x1), int(y1)],..., [int(xn), int(yn)]]}
        - 'region': Список из 4 значений [x, y, w, h] (координаты верхнего левого угла и размеры области)
            Значение - словарь вида {'relative': True/False, 'value': [int(x), int(y)]}
        - 'template': Название и размеры шаблона [image, w, h]
            Значение - словарь вида {
                'relative': True/False, 
                'path': f'{Имя папки бота}/{разрешение экрана}/{шаблон}',  # 'example/800x600/image.png'
                'size': [w, h]
            }
            P.S. Путь шаблона используется относительно папки images/templates/{path}
    Параметр relative означает, что значение может использоваться при любом разрешении экрана.
        В случае с размерами и координатами, каждый следует домножать на высоту экрана для возможности использования 
        значения на разном разрешении окна приложения (учитывать, что такая возможность не всегда есть).
    При переключении на бота словарь заполняется платформой автоматически по всем переменным из setting_variables 
        значениями из БД платформы для этого бота и текущего разрешения окна приложения.
    Задавать список в коде не нужно.
    """
    _variables: dict = {}

    """
    Настройка переменных. 
    Параметр relative означает, что значение может использоваться при любом разрешении экрана.
        В случае с размерами и координатами, каждый будет домножен на высоту экрана для возможности использования 
        значения на разном разрешении окна приложения (учитывать, что такая возможность не всегда есть). При установке 
        этого параметра, значения переменных отображаются в настройках при любом разрешении окна 
        во вкладке 'Относительные'
    Порядок переменных сохраняется при отображении в настройках.
    """
    variables_setting: dict = DictProperty()

    """
    Окна и их наименования (для поиска), используемые в боте.
    Применяются для привязки координат и поиска по шаблонам.
    """
    windows: dict = {
        'main_screen': {'name': ""}
    }

    def __init__(self):
        super(Bot, self).__init__()

        self.app = MDApp.get_running_app()

        self.variables_setting = {
            'Общие настройки': [
                Simple(
                    key='button_delay_ms',
                    name="Дополнительная задержка после действий мыши и клавиатуры (ms)",
                    type='int'
                ),
            ]
        }

    @staticmethod
    def check_freeze():
        MDApp.get_running_app().check_freeze()

    def execute_step(self, task_number, step_number):

        result = {'error': "", 'error_details': "", 'goto': None}

        step = self.get_step(task_number, step_number)

        self.set_empty_log()

        try:
            self.check_freeze()
            step['func']()

        except StopStepError as e:
            result['error'] = str(e)
            result['error_details'] = traceback.format_exc()

            if step.get('on_error') and step['on_error'].get('goto'):
                result['goto'] = step['on_error'].get('goto')

        except Exception as e:
            result['error'] = str(e)
            result['error_details'] = traceback.format_exc()
            self.update_log(details=result['error_details'], level=1, text=result['error'])
            self.save_log()

        return result

    def get_task(self, task_number):
        try:
            task = self.tasks[task_number]
        except Exception as e:
            raise ValueError(f"Не удалось получить Задачу № {task_number}\n" + str(e) +
                             "\nОбратитесь к разработчику бота.")

        return task

    def get_step(self, task_number, step_number):

        task = self.get_task(task_number)

        try:
            step = task['stages'][step_number]
        except Exception as e:
            raise ValueError(f"Не удалось получить Шаг № {step_number} задачи № {task_number}\n" + str(e) +
                             "\nОбратитесь к разработчику бота.")

        return step

    def get_step_fullname(self, task_number, step_number):
        task = self.get_task(task_number)
        step = self.get_step(task_number, step_number)

        return f"{task['name']}: {step['name']}"

    def get_task_tab_buttons_settings(self):
        return self.task_tab_buttons

    def get_task_tab_content(self):
        if self.task_tab_content:
            return self.task_tab_content
        else:
            return Widget()

    def on_variables_setting(self, *_):
        self._variables = {v.key: v for list_v in self.variables_setting.values() for v in list_v}

    def v(self, variable_name):
        """Возвращает значение переменной по ее имени. В случае ее отсутствия в БД вызывает ошибку"""

        if self.need_update_cached_variables_values:
            for var in self._variables.values():
                var.update_cached_value()

            self.set_need_update_cached_variables_values(False)

        variable = self._variables.get(variable_name)

        if not variable:
            raise NameError(f"Переменной с именем '{variable_name}' нет в списке переменных бота")

        return variable.get_cached_value()

    def stop(self):
        return self.app.need_stop_task

    # region Логирование
    def set_empty_log(self):
        # TODO Переделать логирование либо в БД бота, либо ваще убрать, так как сейчас - говно
        """
        Назначение/очистка пустого словаря лога. Назначается каждый раз перед выполнением этапа задачи.
        Для наследуемых классов следует переопределить функцию.
        """
        self.log = {
            'date': int(datetime.now().timestamp()),
            'details': "",
            'image': None,
            'level': 0,
            'text': ""
        }

    def set_need_update_cached_variables_values(self, new_state=True):
        self.need_update_cached_variables_values = new_state

    def open_log(self):
        """
        Выполняется при нажатии на строку с логом. По задумке, функция должна открыть окно с подробной информацией,
        но возможна и другая реализация.
        Для наследуемых классов следует переопределить функцию.
        """
        print(self.log)

    def save_log(self):
        """
        Сохранение словаря лога. Выполняется каждый раз, когда этап задачи завершается с ошибкой.
        Для наследуемых классов следует переопределить функцию.
        """
        image = self.log.get('image')
        if image is not None:
            cv2.imwrite(f"images/screenshots/errors/{self.log['date']}.jpeg", image)

        self.app.db.save_log((
            self.name,
            self.log['date'],
            self.log['level'],
            self.log['text'],
            self.log['details']
        ))

    def update_log(self, details="", **kwargs):
        """
        Записывает значения в лог для ключей, дополняет детали.

        :param details: Всегда дополняются предыдущие детали этапа,
        :param kwargs: Перезаписывают ключи
        """
        self.log.update(kwargs)

        if details:
            self.log['details'] += '\n' + details

    def print_log(self, text):
        # TODO: Заглушка, пока пишем в консоль
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")

    # endregion

    # region Управление мышью и клавиатурой

    def mouse_move(self, x, y, sleep_after=.0, duration=.0):
        self.check_freeze()
        self._mouse_move(x, y, sleep_after, duration)

    def mouse_move_and_click(self, x, y, sleep_after=.0, duration=.0, clicks=1, interval=.0):
        self.check_freeze()
        self._mouse_move(x, y, sleep_after, duration)
        self._mouse_click(x, y, sleep_after, clicks, interval)

    def mouse_click(self, x=None, y=None, sleep_after=.0, clicks=1, interval=.0):
        self.check_freeze()
        self._mouse_click(x, y, sleep_after, clicks, interval)

    def _mouse_move(self, x, y, sleep_after=.0, duration=.0):
        pyautogui.moveTo(x, y, duration=duration)
        time.sleep(.015 + sleep_after + self.v('button_delay_ms') / 1000)

    def _mouse_click(self, x=None, y=None, sleep_after=.0, clicks=1, interval=.0):
        pyautogui.click(x, y, clicks=clicks, interval=interval)
        time.sleep(.015 + sleep_after + self.v('button_delay_ms') / 1000)

    def key_down(self, key, sleep_after=.0):
        self.check_freeze()
        self._key_down(key, sleep_after)

    def _key_down(self, key, sleep_after):
        pyautogui.keyDown(key)
        time.sleep(.025 + sleep_after + self.v('button_delay_ms') / 1000)

    def key_up(self, key, sleep_after=.0):
        self.check_freeze()
        self._key_up(key, sleep_after)

    def _key_up(self, key, sleep_after):
        pyautogui.keyUp(key)
        time.sleep(.025 + sleep_after + self.v('button_delay_ms') / 1000)

    # endregion

    # region Общие функции
    def click_to(self, variable_key, offset_x=.5, offset_y=.5, clicks=1, wait_template=True, accuracy=None, timeout=0):
        """
        Кликает по координатам или найденному шаблону clicks раз с отступом от верхнего левого края offset_x и offset_y в пропорциях
        шаблона (offset_x=.5, offset_y=.5 означает клик в центр шаблона, значения могут превышать 1 или быть
        отрицательными, в таком случае клик произойдет за пределами шаблона)
        """

        variable = self._variables[variable_key]
        variable_value = self.v(variable_key)

        if isinstance(variable, Template):
            self._click_to_template(variable, variable_key, offset_x, offset_y,
                                    clicks, wait_template, accuracy, timeout, variable_value['region'])
        elif isinstance(variable, Coord):
            self._click_to_coord(variable, variable_value, offset_x, offset_y, clicks)

    def _click_to_template(
            self, variable, template, offset_x, offset_y, clicks, wait_template, accuracy, timeout, region):

        def mode_from_type(variable_type):
            if variable_type == 'template':
                mode_: Literal['once', 'all'] = 'once'
            else:
                mode_: Literal['once', 'all'] = 'all'
            return mode_

        _start = datetime.now()
        while True:
            xywh = self.find_template(template, mode=mode_from_type(variable.type), accuracy=accuracy)

            if not xywh and not wait_template:  # Если шаблона нет, то и не нужно на него кликать
                return

            if xywh:
                break

            if self.stop() or (timeout and (datetime.now() - _start).total_seconds() > timeout):
                raise StopStepError(f"Не найден шаблон '{variable.name}'")
            else:
                time.sleep(.5)

        if variable.type == 'template':
            xywh = [xywh, ]

        with mouse_controller:
            for _xywh in xywh:
                x, y, w, h = _xywh
                self.mouse_move_and_click(
                    *to_global(region, [x + w * offset_x, y + h * offset_y]), clicks=clicks, sleep_after=.1)

    def _click_to_coord(self, variable, variable_value, offset_x, offset_y, clicks):
        with mouse_controller:
            if variable.type == 'coord':
                self.mouse_move_and_click(*variable_value, clicks=clicks)
            elif variable.type == 'coord_list':
                for coord in variable_value:
                    self.mouse_move_and_click(*coord, clicks=clicks)
                    time.sleep(.1)
            elif variable.type == 'region':
                x, y, w, h = variable_value
                self.mouse_move_and_click(x + w * offset_x, y + h * offset_y, clicks=clicks)

    def find_template(
            self, template, region=None, accuracy=None, mode: Literal['once', 'all'] = 'once', move_to_1_1=True):
        """
        :param move_to_1_1:
        :param use_mask: Нужно ли использовать маску по альфа-каналу (то есть для прозрачных пнгшек та область, где
            картинка прозрачная, будет всегда совпадение True),
        :param mode: 'once' - возвращает шаблон координаты с максимально подходящим совпадением, 'all' - список
            координат всех найденных шаблонов (с учетом очистки от наложения, то есть в отдельных областях),
        :param region: Область для скриншота в глобальных координатах в пикселях,
        :param template: строка или словарь как в Template.value()
        :param accuracy: Точность совпадения шаблона (от 0 до 1), оптимально 0.89,
        :return: [x, y, w, h] (x,y - левый верхний угол совпадения шаблона, w, h - ширина и высота шаблона)
        """
        self.check_freeze()

        if type(template) == str:
            template = self.v(template)

        if region is None:
            region = template['region']

        img = self.get_screen_region(region, move_to_1_1)

        result_coords = self.match_templates(img, template, mode, accuracy)

        return result_coords

    def get_screen_region(self, region, move_to_1_1):
        if move_to_1_1:
            with mouse_controller:
                self.mouse_move(1, 1)

        img_rgb = np.array(pyautogui.screenshot(region=region))
        img_gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)

        return img_gray

    def match_templates(self, img, template, mode, accuracy=None):

        if type(template) == str:
            template = self.v(template)

        template_gray = template['template_gray']

        template_size = template['size']
        mask = template['mask']
        if not accuracy:
            accuracy = template['normalized_accuracy']

        matches = cv2.matchTemplate(img, template_gray, cv2.TM_CCORR_NORMED, mask=mask)

        # При использовании маски значения могут быть 'бесконечность', отсекаем
        matches[np.isnan(matches)] = 0
        matches[np.isinf(matches)] = 0

        if matches.max() < accuracy:
            coord = cv2.minMaxLoc(matches)[-1]
            img_log = img.copy()
            cv2.rectangle(img_log, coord, [coord[0] + template_size[0], coord[1] + template_size[1]], 255, 2)
            self.log.update({'image': img_log, 'details': f"{str(matches.max())} < {accuracy}"})
            return []

        if mode == 'once':  # Возвращаем координаты максимально совпадающего шаблона
            coord = cv2.minMaxLoc(matches)[-1]
            return [*coord, *template_size]

        elif mode == 'all':  # Очищаем от наложения и возвращаем список координат всех найденных шаблонов

            all_coords = sorted(list(zip(*np.where(matches >= accuracy))), reverse=True)

            # Отсекаем пересекающиеся области, оставляем только уникальные
            unique_coords = non_max_suppression(np.array(
                [(x, y, x + template_size[0], y + template_size[1]) for (y, x) in all_coords]))

            return [
                [start_x, start_y, end_x - start_x, end_y - start_y]
                for (start_x, start_y, end_x, end_y) in unique_coords]

    def wait_for_template(self, template_name, timeout=0, accuracy=None, move_to_1_1=True):
        """Ищет шаблон пока не найдет или не нужно будет завершать задачу"""

        _start = datetime.now()
        while True:
            if self.find_template(template_name, accuracy=accuracy, move_to_1_1=move_to_1_1):
                return True

            if self.stop() or (timeout and (datetime.now() - _start).total_seconds() > timeout):
                raise StopStepError(f"Не найден шаблон '{self._variables[template_name].name}'")
            else:
                time.sleep(.5)

    # region Шаблоны

    def get_template_params(self, template_path, template_size, accuracy=None, use_mask=None):
        """
        :return: template_gray, mask, normalized_accuracy
        """
        template = self.get_template(template_path, template_size)
        mask = self.get_template_mask(template, use_mask)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        normalized_accuracy = self.get_normalized_accuracy(accuracy, template_gray)

        return {'template_gray': template_gray, 'mask': mask, 'normalized_accuracy': normalized_accuracy}

    @staticmethod
    def get_template(path, size):
        if path.startswith("http"):  # Это url
            template_b = requests.get(path).content
            template = np.asarray(bytearray(template_b), dtype="uint8")
            template = cv2.imdecode(template, cv2.IMREAD_UNCHANGED)
        else:
            template = (plt.imread(resource_path(f"images/templates/{path}")) * 255).astype(np.uint8)

        template = cv2.resize(template, size)

        return template

    @staticmethod
    def get_template_mask(template, use_mask):
        if not use_mask:
            return None

        template_size = template.shape[:2]

        mask = np.zeros(template_size).astype('uint8')
        for y in range(template_size[0]):
            for x in range(template_size[1]):
                try:
                    mask[y][x] = template[y][x][3]
                except IndexError:
                    print("Попытка получить маску по шаблону без 4ого alpha-канала прозрачности")
                    return None

        return mask

    @staticmethod
    def get_normalized_accuracy(accuracy, template):
        # Редактирование точности (алгоритм поиска: светлые картинки на светлом фоне выделяет сильнее)
        # Все пиксели, кроме пустых (они будут вырезаны маской) и черных (так уж получилось, но это не влияет)
        if accuracy is None:
            accuracy = .89

        avg_value = np.average(template[template != 0])
        if avg_value < 40:
            accuracy -= .03
        elif avg_value > 100:
            accuracy += .03
        else:
            accuracy += (avg_value - 70) / 1000

        return accuracy

    # endregion

    # Если нужно узнать инфу окон всех открытых приложений
    @staticmethod
    def all_windows():

        def _callback(hwnd, _extra):
            rect = win32gui.GetWindowRect(hwnd)
            x = rect[0]
            y = rect[1]
            w = rect[2] - x
            h = rect[3] - y
            print("Window %s:" % win32gui.GetWindowText(hwnd))
            print("\tLocation: (%d, %d)" % (x, y))
            print("\t    Size: (%d, %d)" % (w, h))

        win32gui.EnumWindows(_callback, None)

    # endregion


# region Окна

def get_window_param(window_key, p: Literal["xywh", "xy", "wh", "h", "xywh_hwnd"] = 'xywh'):
    """
    :param window_key: Ключ окна из bot.windows. Если нужно узнать имя окна приложения, см. функцию all_windows()
    :param p: Параметр возвращаемых данных
    :return [x, y, w, h]: xy - верхний левый угол, wh - ширина, высота
    """

    window_settings = MDApp.get_running_app().bot.windows.get(window_key)

    if not window_settings['name']:
        return [0, 0, GetSystemMetrics(0), GetSystemMetrics(1)]

    hwnd = win32gui.FindWindow(None, window_settings['name'])

    try:
        window_ext = win32gui.GetWindowRect(hwnd)  # Внешние рамки окна с учетом теней и шапки
    except pywintypes.error:
        raise WindowsError(f"Не найдено окно с именем {window_settings['name']}")

    header_rect = RECT()
    DWMWA_CAPTION_BUTTON_BOUNDS = 5  # Параметр для получения координат кнопок в шапке окна
    dwmapi.DwmGetWindowAttribute(HWND(hwnd), DWORD(DWMWA_CAPTION_BUTTON_BOUNDS),
                                 ctypes.byref(header_rect), ctypes.sizeof(header_rect))
    header_height = header_rect.bottom - header_rect.top  # Высота шапки (где крестик, свернуть и тд)
    header_height += 1 if header_height else 0

    rect = RECT()
    DWMWA_EXTENDED_FRAME_BOUNDS = 9  # Параметр для получения координат окна без теней
    dwmapi.DwmGetWindowAttribute(HWND(hwnd), DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
                                 ctypes.byref(rect), ctypes.sizeof(rect))

    is_fullscreen = not header_height or (window_ext[1] - rect.top != 0)
    indent = [
        window_ext[0] - rect.left - int(not is_fullscreen),
        header_height,
        window_ext[2] - rect.right + int(not is_fullscreen),
        window_ext[3] - rect.bottom + int(not is_fullscreen)
    ]

    x = window_ext[0] - indent[0]
    y = window_ext[1] + indent[1]
    w = window_ext[2] - indent[2] - x
    h = window_ext[3] - indent[3] - y

    expression = window_settings.get('expression')

    if expression:
        x, y, w, h = map(eval, expression)

    if p == 'xy':
        return [x, y]
    elif p == 'wh':
        return [w, h]
    elif p == 'h':
        return h
    elif p == 'xywh_hwnd':
        return [x, y, w, h, hwnd]
    else:
        return [x, y, w, h]


def to_pixels(relative_coords, h):
    """Перевод относительных координат в абсолютные по текущей высоте окна"""
    return [int(round(z * h)) for z in relative_coords]


def to_global(window_pos, coords):
    """Перевести координаты из относительных окна приложения в абсолютные (относительно левого верхнего угла экрана)
    Переводит только первые 2 значения из списка, остальное оставляет как есть"""

    new_coords = [window_pos[0] + coords[0], window_pos[1] + coords[1]]

    if len(coords) > 2:
        new_coords.extend(coords[2:])

    return new_coords


# endregion


# region Типы переменных

@dataclass
class Variable:
    """"""

    """Кешированное значение переменной, чтобы не запрашивать из БД"""
    cached_value = None

    """Допустимые значения типа для класса"""
    verifiable = {
        'type': []
    }

    """Ключ переменной"""
    key: str

    """Тип значения. В зависимости от типа разная обработка данных"""
    type: str

    """Имя переменной. Для отображения пользователю в настройках"""
    name: str = ""

    """Раздел в настройках"""
    section: str = ""

    """
    Текущее состояние окна, для которого указана переменная.
    Если переменная не зависит от окна, то ключом будет 'any'. Но ключ должен быть всегда при сохранении 
    и получении переменной из БД.
    Каждый наследуемый объект должен сам обновлять информацию об окне в моменты: 
        а) получения переменной из БД, 
        б) получения переменной со скриншота
    """
    window_info = {'xywh': [0, 0, 0, 0], 'pos': [0, 0], 'size': [0, 0], 'key': 'any'}

    def __init__(self, **kwargs):

        self.__dict__.update({k: v for k, v in kwargs.items() if k not in self.verifiable})

        for key, val in kwargs.items():
            if key not in self.verifiable or (key in self.verifiable and val in self.verifiable[key]):
                setattr(self, key, val)
            else:
                raise ValueError(
                    f"Для аргумента '{key}' значение '{val}' не входит в список допустимых {self.verifiable[key]}")

    def get_from_screenshot(self):
        raise AttributeError("Доступен только ручной ввод значения")

    def fullname(self):
        return self.name

    def get_window_key(self):
        return self.window_info['key']

    def update_cached_value(self):
        self.cached_value = self.value()

    def value(self):
        return None

    def get_cached_value(self):
        return self.cached_value


class Coord(Variable):
    """Хранит координаты [x, y], списки координат [[x,y], [x1, y1]] или области [x, y, w, h]"""

    verifiable: dict = {
        'type': ['coord', 'coord_list', 'region'],
        'snap_mode': ['lt', 'rt', 'lb', 'rb', 'ct']
    }

    """Значение выражено долями единицы относительно высоты окна"""
    relative: bool = True

    """Привязка к углу окна. lt - left-top и тд"""
    snap_mode: str = 'lt'

    """Родительское окно, к которому привязаны координаты"""
    window: str = 'main_screen'

    def fullname(self):
        return f"{self.name} ({self.snap_mode})"

    def snap(self, v: list or tuple, reverse=False):
        """
        Перевязывает координаты от нестандартной привязки к левому верхнему углу окна.
        При повторном применении меняет обратно. Функцией можно сделать точкой отсчета как self.snap_mode, так и 'lt'.
        Изменяет только первые 2 элемента списка, остальные оставляет как есть
        """

        if self.snap_mode == 'rt':  # Привязка была к правому верхнему углу
            new_v = [self.window_info['size'][0] - v[0], v[1]]
        elif self.snap_mode == 'lb':  # Привязка была к левому нижнему углу
            new_v = [v[0], self.window_info['size'][1] - v[1]]
        elif self.snap_mode == 'rb':  # Привязка была к правому нижнему углу
            new_v = [self.window_info['size'][0] - v[0], self.window_info['size'][1] - v[1]]
        elif self.snap_mode == 'ct':  # Привязка была к середине верхней рамки
            new_v = [v[0] + self.window_info['size'][0] / 2 * (1 if reverse else -1), v[1]]
        else:  # Была стандартная привязка 'lt'
            return v

        if len(v) > 2:
            new_v.extend(v[2:])

        return new_v

    def value(self):

        value = self._value()

        if self.relative:
            value = to_pixels(value, self.window_info['size'][1])

        if self.type == 'coord_list':
            pairs = zip(value[::2], value[1::2])  # Общий список соединяем попарно
            value = [to_global(self.window_info['pos'], self.snap(pair, True)) for pair in pairs]
        else:
            value = to_global(self.window_info['pos'], self.snap(value, True))

        return value

    def _value(self, allowed_empty=False):

        self.update_window_info()

        app = MDApp.get_running_app()

        value_str = app.db.get_bots_variable(
            app.bot.key,
            self.key,
            self.window_info['key']
        )

        if not value_str:
            if allowed_empty:
                return [[]] if self.type == 'coord_list' else []
            else:
                raise NameError(f"Значение переменной '{self.name}' не найдено для окна '{self.window_info['key']}'")

        value = list(map(float, value_str.split(", ")))

        return value

    def value_for_settings(self):

        try:
            value = self._value(True)
        except WindowsError:  # Если окно не открыто, то ничего не возвращаем в настройки
            return ""

        return ", ".join(map(str, value))

    def get_from_screenshot(self):

        self.update_window_info()

        def click(event, click_x, click_y, _flags, _params):
            nonlocal click1, img, new_value, point1

            def target(_img):
                cv2.line(_img, (click_x - 20, click_y), (click_x - 5, click_y), (0, 0, 255), 2)
                cv2.line(_img, (click_x, click_y - 20), (click_x, click_y - 5), (0, 0, 255), 2)
                cv2.line(_img, (click_x + 20, click_y), (click_x + 5, click_y), (0, 0, 255), 2)
                cv2.line(_img, (click_x, click_y + 20), (click_x, click_y + 5), (0, 0, 255), 2)

            def to_relative(_value):
                if not self.relative:
                    return _value

                return round(_value / self.window_info['size'][1], 4)

            if event == cv2.EVENT_LBUTTONDOWN:
                click1 = True
                point1 = (click_x, click_y)
            elif event == cv2.EVENT_MOUSEMOVE and click1:
                if self.type == 'region':
                    img_copy = img.copy()
                    cv2.rectangle(img_copy, point1, (click_x, click_y), (0, 0, 255), 2)
                    cv2.imshow("Image", img_copy)
            elif event == cv2.EVENT_LBUTTONUP:
                click1 = False
                if self.type == 'coord':
                    img_copy = img.copy()
                    target(img_copy)
                    cv2.imshow("Image", img_copy)
                elif self.type == 'coord_list':
                    target(img)
                    cv2.imshow("Image", img)

                if self.type == 'coord' or self.type == 'coord_list':
                    current_value = ", ".join(
                        map(str, map(to_relative, self.snap([click_x, click_y]))))

                    if self.type == 'coord_list' and new_value:
                        new_value = ", ".join([new_value, current_value])
                    else:
                        new_value = current_value

                elif self.type == 'region':
                    s_point = [
                        min([point1[0], click_x]),
                        min([point1[1], click_y])
                    ]
                    e_point = [
                        max([point1[0], click_x]),
                        max([point1[1], click_y])
                    ]
                    new_value = ", ".join(map(str, [
                        *list(map(to_relative, self.snap(s_point))),
                        to_relative(e_point[0] - s_point[0]),
                        to_relative(e_point[1] - s_point[1])
                    ]))

                else:
                    raise ValueError(f"Невозможно определить значение для типа: {self.type}")

        time.sleep(1)

        img_rgb = pyautogui.screenshot(region=self.window_info['xywh'])
        img = cv2.cvtColor(np.array(img_rgb), 2)

        click1 = False
        point1 = (0, 0)
        new_value = ""

        cv2.namedWindow("Image")
        cv2.setMouseCallback("Image", click)
        cv2.imshow("Image", img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

        return new_value

    def update_window_info(self):
        xywh = get_window_param(self.window)
        self.window_info = {
            'xywh': xywh,
            'pos': xywh[:2],
            'size': xywh[-2:],
            'key': self.window if self.relative else f'{self.window} {"x".join(list(map(str, xywh[-2:])))}'
        }


class Simple(Variable):
    """Хранит простые данные: числа, строки и тд"""

    verifiable = {
        'type': ['str', 'int', 'float', 'bool']
    }

    def value(self, allowed_empty=False):
        app = MDApp.get_running_app()

        value_str = app.db.get_bots_variable(
            app.bot.key,
            self.key,
            "any")

        if not value_str:
            if allowed_empty:
                return eval(f"{self.type}()")
            else:
                raise NameError(f"Значение переменной '{self.name}' не найдено")

        return eval(f"{self.type}(value_str)")

    def value_for_settings(self):
        """Булево возвращается как булево, остальные значения конвертируются в текст"""

        value = self.value(True)
        return value if self.type == 'bool' else str(value)


class Template(Variable):
    """
    Хранит шаблоны: путь до картинки и размеры шаблона,
    функционально - ссылку на область поиска (если не задано - поиск по всему окну)
    """

    """Ссылка на объект Coord(type='region')"""
    region: Coord

    verifiable = {
        'type': ['template', 'templates']
    }

    """Значение выражено долями единицы относительно высоты окна"""
    relative: bool = True

    """Родительское окно, к которому привязаны координаты"""
    window: str = 'main_screen'

    def fullname(self):
        return f"{self.name} ({self.region.snap_mode})"

    def get_from_screenshot(self):

        self.update_window_info()

        def click(event, click_x, click_y, _flags, _params):
            nonlocal rectangles, img, new_value

            def to_relative(_value):
                if not self.relative:
                    return _value

                return round(_value / self.window_info['size'][1], 4)

            if event == cv2.EVENT_LBUTTONDOWN:
                rectangles['l']['click1'] = True
                rectangles['l']['active'] = True
                rectangles['l']['point1'] = (click_x, click_y)
            elif event == cv2.EVENT_RBUTTONDOWN:
                rectangles['r']['click1'] = True
                rectangles['r']['active'] = True
                rectangles['r']['point1'] = (click_x, click_y)
            elif event == cv2.EVENT_MOUSEMOVE and (rectangles['l']['click1'] or rectangles['r']['click1']):
                img_copy = img.copy()
                if rectangles['l']['click1']:
                    rectangles['l']['point2'] = (click_x, click_y)
                if rectangles['r']['click1']:
                    rectangles['r']['point2'] = (click_x, click_y)
                if rectangles['l']['active']:
                    cv2.rectangle(img_copy, rectangles['l']['point1'], rectangles['l']['point2'], (39, 116, 240), 2)
                if rectangles['r']['active']:
                    cv2.rectangle(img_copy, rectangles['r']['point1'], rectangles['r']['point2'], (0, 0, 255), 2)
                cv2.imshow("Image", img_copy)
            elif event == cv2.EVENT_LBUTTONUP or event == cv2.EVENT_RBUTTONUP:
                b = 'l' if event == cv2.EVENT_LBUTTONUP else 'r'
                rectangles[b]['click1'] = False

                if not rectangles['l']['active'] and not rectangles['r']['active']:
                    new_value = ""
                    return

                for rectangle in rectangles.values():
                    if rectangle['active']:
                        s_point = [
                            min([rectangle['point1'][0], rectangle['point2'][0]]),
                            min([rectangle['point1'][1], rectangle['point2'][1]])
                        ]

                        e_point = [
                            max([rectangle['point1'][0], rectangle['point2'][0]]),
                            max([rectangle['point1'][1], rectangle['point2'][1]])
                        ]

                        rectangle['xywh'] = [
                            s_point[0],
                            s_point[1],
                            e_point[0] - s_point[0],
                            e_point[1] - s_point[1]
                        ]

                if not rectangles['r']['active']:  # Шаблон не указан явно, берем его равным региону
                    rectangles['r']['xywh'] = rectangles['l']['xywh']
                elif not rectangles['l']['active']:  # Регион не указан явно, берем все окно приложения
                    rectangles['l']['xywh'] = [0, 0] + self.window_info['xywh'][-2:]

                app = MDApp.get_running_app()
                templates_path = app.bot.key
                if self.relative:
                    directory = os.path.join(templates_path, "relative")
                else:
                    directory = os.path.join(templates_path, 'x'.join(map(str, self.window_info['size'])))
                templates_path = os.path.join(r"images\templates", directory)
                if not os.path.exists(templates_path):
                    os.makedirs(templates_path)
                template_name = f"{self.key}.png"
                cv2.imwrite(
                    os.path.join(templates_path, template_name),
                    img[
                    rectangles['r']['xywh'][1]:rectangles['r']['xywh'][1] + rectangles['r']['xywh'][-1],
                    rectangles['r']['xywh'][0]:rectangles['r']['xywh'][0] + rectangles['r']['xywh'][-2]
                    ]
                )

                size = ", ".join(map(str, map(to_relative, rectangles['r']['xywh'][-2:])))

                region = ", ".join(map(str, map(to_relative, self.region.snap(rectangles['l']['xywh']))))

                new_value = ", ".join([size, template_name, region])

        time.sleep(1)

        img_rgb = pyautogui.screenshot(region=self.window_info['xywh'])
        img = cv2.cvtColor(np.array(img_rgb), 2)

        rectangles = {
            'l': {
                'click1': False,
                'point1': (0, 0),
                'point2': (0, 0),
                'active': False,
                'xywh': []
            },
            'r': {
                'click1': False,
                'point1': (0, 0),
                'point2': (0, 0),
                'active': False,
                'xywh': []
            }
        }
        new_value = ""

        cv2.namedWindow("Image")
        cv2.setMouseCallback("Image", click)
        cv2.imshow("Image", img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

        return new_value

    def value(self):
        value = self._value()

        path = value[2]
        template_size = list(map(float, value[:2]))
        region = self.region.value()

        if self.relative:
            template_size = to_pixels(template_size, self.window_info['size'][1])
        else:
            template_size = list(map(int, template_size))

        window_dir = "relative" if self.relative else 'x'.join(map(str, self.window_info['size']))

        template_path = f"{MDApp.get_running_app().bot.key}/{window_dir}/{path}"

        value = {
            'path': template_path,
            'size': template_size,
            'region': region
        }

        template_params_by_bot = MDApp.get_running_app().bot.get_template_params(template_path, template_size)

        value.update(template_params_by_bot)

        return value

    def _value(self, allowed_empty=False):

        self.update_window_info()

        app = MDApp.get_running_app()

        value_str = app.db.get_bots_variable(
            app.bot.key,
            self.key,
            self.window_info['key']
        )

        if not value_str:
            if allowed_empty:
                return []
            else:
                raise NameError(f"Значение переменной '{self.name}' не найдено для окна '{self.window_info['key']}'")

        value = value_str.split(", ")

        return value

    def value_for_settings(self):
        """Возвращает текст из списка [size[0], size[1], path]"""

        try:
            value = self._value(True)
            return ", ".join([*value, self.region.value_for_settings()])
        except WindowsError:  # Если окно не открыто, то ничего не возвращаем в настройки
            return ""

    def update_window_info(self):
        xywh = get_window_param(self.window)
        self.window_info = {
            'xywh': xywh,
            'pos': xywh[:2],
            'size': xywh[-2:],
            'key': self.window if self.relative else f'{self.window} {"x".join(list(map(str, xywh[-2:])))}'
        }
# endregion
