import threading
import time
import cv2
import pyautogui
import numpy as np
import pywintypes
import win32gui
from kivymd.app import MDApp


def simulacrum(stages):
    app = MDApp.get_running_app()

    for stage in stages:
        if need_stop_action():
            if not app.current_action.timer:  # Отвалился по таймингу
                # Можно прописать, что делать, когда тайминг действия закончился. Сейчас - начинаем заново
                app.main.do_next_action(0)
            return

        app.set_status(f"Выполняю: {stage['text']}", True)
        app.update_current_stage(stage['index'])

        try:
            error = eval(stage['func'])
        except Exception as e:
            error = str(e)

        if error:
            app.update_current_stage(stage['index'], error)
            return

    app.main.do_next_action()


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
    pyautogui.screenshot(f"images/screenshots/_desktop.png", )
    img_rgb = cv2.imread(f"images/screenshots/_desktop.png")
    img_gray = cv2.cvtColor(img_rgb, cv2.COLOR_BGR2GRAY)
    template = cv2.imread(f"images/templates/poe.png", 0)
    res = cv2.matchTemplate(img_gray, template, cv2.TM_CCOEFF_NORMED)
    if res.max() >= 0.70:
        _, _, _, coord = cv2.minMaxLoc(res)
    else:
        return "Не найден ярлык ПОЕ на экране"

    pyautogui.moveTo(coord)
    pyautogui.click(clicks=2)
    time.sleep(.5)


def authorization():
    time.sleep(2)


def choice_character():
    time.sleep(2)


# endregion


# region Общие функции

# Найти по шаблону
def find_by_template(region, template, accuracy=.8, file_to_save=""):
    """
    :param region: В долях единицы
    :param template: Имя файла, будет использоваться такой путь: images/templates/{template}.png
    :param accuracy: Точность совпадения шаблона (от 0 до 1), оптимально 0.7 - 0.9
    :param file_to_save: Если указать им файла, будет сохранен по пути images/screenshots/{file_to_save}.png
    :return:
    """
    img_rgb = pyautogui.screenshot(file_to_save, region)
    img_bgr = cv2.cvtColor(np.array(img_rgb), cv2.COLOR_RGB2BGR)
    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    template = cv2.imread(f"images/templates/poe.png", 0)
    res = cv2.matchTemplate(img_gray, template, cv2.TM_CCOEFF_NORMED)
    if res.max() >= 0.70:
        _, _, _, coord = cv2.minMaxLoc(res)
    else:
        return "Не найден ярлык ПОЕ на экране"

    pyautogui.moveTo(coord)
    pyautogui.click(clicks=2)
    time.sleep(.5)


#  region_to_pixels
def rtp(region):
    """
    Получает координаты (region) в долях единицы, возвращает в пикселях относительно разрешения экрана и положения окна.
    :param region: [x, y] в долях единицы от верхнего левого угла окна приложения. Например [.323, .761]
    :return: [x, y] в пикселях, например [620, 822] для значения [.323, .761] и экрана 1920x1080.
    Если окно приложения находится в правой нижней части экрана, например левый верхний угол окна в точке (1000, 500),
    а сам размер окна 920x580, то вернется [1297, 941], то есть [1000 + .323 * 920, 500 + .761 * 580]
    """
    x, y, w, h = get_window_coord("Path of Exile")
    return [x + region[0] * w, y + region[1] * h]


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
        return f"Не запущено приложение {window_name}"
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
