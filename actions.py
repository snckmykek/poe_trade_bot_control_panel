import os.path
import threading
import time
import cv2
import keyboard as keyboard
import pyautogui
import numpy as np
import pywintypes
import win32gui
from win32api import GetSystemMetrics
from kivy.clock import Clock
from kivymd.app import MDApp

import gv


def do_current_action():
    app = MDApp.get_running_app()
    current_action = app.current_action
    action_tab = app.main.ids.action_tab

    for stage in current_action.stages:
        if need_stop_action():
            if not app.current_action.timer and app.current_action.have_timer:  # Отвалился по таймингу
                current_action.func_timer_over()
            return

        Clock.schedule_once(lambda *_: action_tab.report_current_stage(stage['index']))

        try:
            error = eval(stage['func'])
        except Exception as e:
            error = str(e)

        if error:
            Clock.schedule_once(lambda *_: action_tab.report_current_stage(stage['index'], error))
            return

    Clock.schedule_once(lambda *_: app.do_next_action())


def need_stop_action():
    app = MDApp.get_running_app()

    if app.need_stop_action:
        if app.need_pause:
            app.set_running(False)
        return True
    else:
        return False


# region Вход

def start_poe():

    time.sleep(1.5)

    variables = MDApp.get_running_app().action_variables

    xywh = find_by_template([0, 0, GetSystemMetrics(0), GetSystemMetrics(1)], variables['poe_icon'])
    if not xywh:
        return "Не найден ярлык ПОЕ на основном экране"
    else:
        x, y, w, h = xywh

    pyautogui.moveTo(x + w/2, y + h/2)
    pyautogui.click(clicks=2)

    # Ждем, пока нормально запустится ПОЕ (при запуске окно перемещается микросекунду)
    window_name = "Path of Exile"
    window_xywh = None
    while True:
        if need_stop_action():
            return f"Не запущено окно с именем {window_name}"
        time.sleep(.1)

        _window_xywh = get_window_coord(window_name)
        # Только когда в одном и том же месте окно находится - всё ок
        if _window_xywh and window_xywh == _window_xywh:
            # Выводим на передний план окно (но расположение слетает в 0,0)
            hwnd = win32gui.FindWindow(None, window_name)
            win32gui.SetForegroundWindow(hwnd)
            return
        else:
            window_xywh = _window_xywh


def authorization():
    variables = MDApp.get_running_app().action_variables

    window_name = "Path of Exile"
    window_xywh = get_window_coord(window_name)
    if not window_xywh:
        return f"Не запущено окно с именем {window_name}"

    template = variables['template_email']
    if not click_to_template(window_xywh, template, offset_x=2):
        return f"Не найден шаблон {template} на экране в области окна ПОЕ"
    keyboard.write(variables['login'], delay=0)

    template = variables['template_password']
    if not click_to_template(window_xywh, template, offset_x=2):
        return f"Не найден шаблон {template} на экране в области окна ПОЕ"
    keyboard.write(variables['password'], delay=0)

    template = variables['template_login']
    if not click_to_template(window_xywh, template):
        return f"Не найден шаблон {template} на экране в области окна ПОЕ"
    keyboard.write(variables['password'], delay=0)


def choice_character():
    variables = MDApp.get_running_app().action_variables

    window_name = "Path of Exile"
    window_xywh = get_window_coord(window_name)
    if not window_xywh:
        return f"Не запущено окно с именем {window_name}"

    template = variables['template_character']
    if not click_to_template(window_xywh, template, clicks=2):
        return f"Не найден шаблон {template} на экране в области окна ПОЕ"


# endregion

# region Выход из ПОЕ на перерыв
def logout():
    time.sleep(2)


# endregion

# region Продажа. Подготовка

def check_stash():
    time.sleep(2)


def wait_trade_info():
    time.sleep(2)


# endregion

# region Продажа. Запрос сделки
def deal_request():
    time.sleep(2)


def take_currency():
    time.sleep(2)


def teleport():
    time.sleep(2)


# endregion

# region Продажа. Сделка
def wait_trade():
    time.sleep(2)


def put_currency():
    time.sleep(2)


def check_items():
    time.sleep(2)


def wait_confirm():
    time.sleep(2)


# endregion

# region Продажа. ТП в свой хайдаут
def go_home():
    time.sleep(2)


# endregion

# region test

def test():
    time.sleep(3)


#endregion

# region Общие функции

def click_to_template(region, template, offset_x=.5, offset_y=.5, clicks=1):
    xywh = None
    while not xywh:
        xywh = find_by_template(region, template)
        if need_stop_action():
            return False
    x, y, w, h = xywh

    pyautogui.moveTo(to_global(region, [x + w * offset_x, y + h * offset_y]))
    pyautogui.click(clicks=clicks)
    time.sleep(.1)

    return True


# Перевести координаты из относительных окна приложения в абсолютные (относительно левого верхнего угла экрана)
def to_global(window_coords, coords):
    return [window_coords[0] + coords[0], window_coords[1] + coords[1]]


# Найти по шаблону
def find_by_template(region, template_path, accuracy=.8, file_to_save=""):
    """
    :param region: Область скриншота
    :param template_path: Часть пути до файла, будет использоваться такой путь: images/templates/{template_path}
    :param accuracy: Точность совпадения шаблона (от 0 до 1), оптимально 0.7 - 0.9
    :param file_to_save: Если указать имя файла, будет сохранен по пути images/screenshots/{file_to_save}.png
    :return: [x, y, w, h] (x,y - левый верхний угол совпадения шаблона, w,h - ширина и высота шаблона)
    """

    if file_to_save:
        img_rgb = pyautogui.screenshot(f"images/screenshots/{file_to_save}.png", region=region)
    else:
        img_rgb = pyautogui.screenshot(region=region)
    img_bgr = cv2.cvtColor(np.array(img_rgb), cv2.COLOR_RGB2BGR)
    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    template = cv2.imread(f"images/templates/{template_path}", 0)
    res = cv2.matchTemplate(img_gray, template, cv2.TM_CCOEFF_NORMED)
    if res.max() >= accuracy:
        _, _, _, coord = cv2.minMaxLoc(res)
    else:
        return

    return [*coord, template.shape[1], template.shape[0]]


def get_window_coord(window_name):
    """
    Если нужно узнать имя окна приложения, см. функцию print_all_windows()
    :param window_name:
    :return:
    """

    hwnd = win32gui.FindWindow(None, window_name)
    try:
        rect = win32gui.GetWindowRect(hwnd)
    except pywintypes.error:
        return

    x = rect[0]
    y = rect[1]
    w = rect[2] - x
    h = rect[3] - y

    return [x, y, w, h]


# endregion

# region Служебные. Для разработки


# Если нужно узнать имя окна любого приложения
def print_all_windows():
    import win32gui

    def _callback(hwnd, extra):
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
