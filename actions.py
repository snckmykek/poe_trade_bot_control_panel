import math
import os.path
import threading
import time
from datetime import datetime
from operator import itemgetter

import cv2
import keyboard as keyboard
import pyautogui
import numpy as np
import pywintypes
import requests
import win32gui
from win32api import GetSystemMetrics
from kivy.clock import Clock
from kivymd.app import MDApp

import gv


def do_current_action():
    app = MDApp.get_running_app()
    current_action = app.current_action
    action_tab = app.main.ids.action_tab

    # time.sleep(2)  # Для теста !

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

    Clock.schedule_once(lambda *_: app.do_next_action())  # !


def need_stop_action():
    app = MDApp.get_running_app()

    if app.need_stop_action:
        if app.need_pause:
            app.set_running(False)
        return True
    else:
        time.sleep(.1)
        return False


# region Вход

def start_poe():
    time.sleep(1.5)

    variables = MDApp.get_running_app().action_variables
    window_xywh = [0, 0, GetSystemMetrics(0), GetSystemMetrics(1)]
    xywh = find_by_template(window_xywh[-1], window_xywh, variables['poe_icon'])
    if not xywh:
        return "Не найден ярлык ПОЕ на основном экране"
    else:
        x, y, w, h = xywh

    pyautogui.moveTo(x + w / 2, y + h / 2)
    pyautogui.click(clicks=2)

    # Ждем, пока нормально запустится ПОЕ (при запуске окно перемещается микросекунду)
    window_name = "Path of Exile"
    window_xywh = None
    while True:
        if need_stop_action():
            return f"Не запущено окно с именем {window_name}"

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

# region Продажа. Запросы на ПОЕ трейд
def start_poe_trade():
    variables = MDApp.get_running_app().action_variables

    variables.update({'swag': None})
    variables.update({'deals': None})
    variables.update({'current_deal': None})
    variables.update({'divine_price': 0})
    variables.update({'last_10_completed_deals': []})

    threading.Thread(target=lambda *_: poetrade_loop(), daemon=True).start()


def poetrade_loop():
    app = MDApp.get_running_app()
    variables = app.action_variables

    update_swag_info()
    update_divine_price()

    while True:
        if app.need_pause:
            return

        _datetime = datetime.now()

        update_offer_list()

        _interval = float(variables['poetrade_info_update_frequency']) - (datetime.now() - _datetime).total_seconds()
        if _interval > 0:
            time.sleep(_interval)


def update_swag_info():
    variables = MDApp.get_running_app().action_variables
    variables['swag'] = {'chaos': 4324, 'divine': 193}


def update_divine_price():
    variables = MDApp.get_running_app().action_variables

    prices = [deal['exchange_amount'] / deal['item_amount'] for deal in get_deals(("divine",), ("chaos",))]
    avg = sum(prices) / len(prices)

    # Вырезаем прайсфиксерные цены
    _prices = prices.copy()
    for _price in _prices:
        if abs((_price - avg) / avg) > 0.05:  # При отклонении больше чем на 5% от среднего - убираем из списка
            prices.remove(_price)  # Удаляет первый совпавший элемент
            avg = sum(prices) / len(prices)  # Пересчет среднеарифметического

    variables['divine_price'] = round(sum(prices) / len(prices))


def update_offer_list():
    app = MDApp.get_running_app()
    variables = app.action_variables
    items_i_want = [
        {
            'item': item_settings['item'],
            'max_price': item_settings['max_price'],
            'bulk_price': item_settings['bulk_price'],
            'image': item_settings['image'],
            'max_qty': item_settings['max_qty']
        } for item_settings in gv.db.af_get_items(app.type)
        if (
                item_settings['use'] and item_settings['max_price']
                and item_settings['bulk_price'] and item_settings['max_qty']
        )
    ]

    variables['deals'] = get_deals(items_i_want, ("chaos",))


# endregion

# region Продажа. Подготовка
def go_home():
    variables = MDApp.get_running_app().action_variables

    window_name = "Path of Exile"
    window_xywh = get_window_coord(window_name)
    if not window_xywh:
        return f"Не запущено окно с именем {window_name}"

    # Ждем/проверяем запуск игры
    template = variables['template_game_loaded']
    region = to_pixels(variables['region_game_loaded'], window_xywh[-1])
    xywh = None
    while not xywh:
        xywh = find_by_template(window_xywh[-1], region, template)
        if need_stop_action():
            return f"Не найден шаблон {template} на экране в области окна ПОЕ"

    pyautogui.press('enter')
    time.sleep(.02)
    keyboard.write('/hideout', delay=0)
    time.sleep(.02)
    pyautogui.press('enter')


def check_stash():
    variables = MDApp.get_running_app().action_variables

    window_name = "Path of Exile"
    window_xywh = get_window_coord(window_name)
    if not window_xywh:
        return f"Не запущено окно с именем {window_name}"

    # Ждем/проверяем запуск игры
    template = variables['template_stash_title']
    xywh = None
    while not xywh:
        xywh = find_by_template(window_xywh[-1], window_xywh, template)
        if need_stop_action():
            return f"Не найден шаблон {template} на экране в области окна ПОЕ"


# endregion

# region Выход из ПОЕ на перерыв
def logout():
    pyautogui.hotkey("alt", "f4")

    window_name = "Path of Exile"
    while get_window_coord(window_name):
        if need_stop_action():
            return f"Не смог выйти из ПОЕ"


# endregion

# region Продажа. Ожидание очереди сделок
def wait_trade_info():
    variables = MDApp.get_running_app().action_variables

    while not variables.get("swag"):
        if need_stop_action():
            return "Не дождался инфы о валюте в стеше"

    while not variables.get("divine_price"):
        if need_stop_action():
            return "Не дождался инфы о цене дивайна"

    while not variables.get("deals"):
        if need_stop_action():
            return "Не дождался инфы о сделках"


# endregion

# region Продажа. Запрос сделки
def set_current_deal():
    variables = MDApp.get_running_app().action_variables
    current_deal = variables['deals'].pop(0)
    # TODO: чекнуть на актуальность сделки, пока берем как есть
    while current_deal['id'] in variables['last_10_completed_deals']:
        current_deal = variables['deals'].pop(0)

    variables['current_deal'] = current_deal


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
    variables = MDApp.get_running_app().action_variables
    variables['last_10_completed_deals'].insert(0, variables['current_deal']['id'])
    variables['last_10_completed_deals'] = variables['last_10_completed_deals'][:10]
    time.sleep(2)


# endregion

# region test

def test():
    time.sleep(3)


# endregion

# region Общие функции

def click_to_template(region, template, offset_x=.5, offset_y=.5, clicks=1):
    xywh = None
    while not xywh:
        xywh = find_by_template(region[-1], region, template)
        if need_stop_action():
            return False
    x, y, w, h = xywh

    pyautogui.moveTo(to_global(region, [x + w * offset_x, y + h * offset_y]))
    pyautogui.click(clicks=clicks)
    time.sleep(.1)

    return True


# Перевести координаты из относительных окна приложения в абсолютные (относительно левого верхнего угла экрана)
# Переводит только первые 2 значения из списка, остальное оставляет как есть
def to_global(window_coords, coords):
    new_coords = [window_coords[0] + coords[0], window_coords[1] + coords[1]]

    if len(coords) > 2:
        new_coords.extend(coords[2:])

    return new_coords


# Найти по шаблону
def find_by_template(h, region, template_settings, accuracy=.8, file_to_save=""):
    """
    :param h: Высота приложения
    :param region: Область скриншота
    :param template_settings: Словарь.
        path: Часть пути до файла, будет использоваться такой путь: images/templates/{template_path}
        size: [x, y] в долях единицы относительно высоты приложения h
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
    template = cv2.imread(f"images/templates/{template_settings['path']}", 0)
    template = cv2.resize(template, to_pixels(template_settings['size'], h))
    res = cv2.matchTemplate(img_gray, template, cv2.TM_CCOEFF_NORMED)
    if res.max() >= accuracy:
        coord = cv2.minMaxLoc(res)[-1]
    else:
        return

    return [*coord, template.shape[1], template.shape[0]]


def to_pixels(relative_coords, h):
    return [int(round(z * h)) for z in relative_coords]


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


def send_to_chat(message):
    pyautogui.press('enter')
    time.sleep(.02)
    keyboard.write(message, delay=0)
    time.sleep(.02)
    pyautogui.press('enter')


def get_deals(items_i_want, items_i_have, min_stock=1, qty_deals=20):
    """
    :param qty_deals:
    :param items_i_want: Список Словарей
    :param items_i_have: Список строк
    :param min_stock:
    :return: Отсортированный по профиту список сделок
    """
    deals = []

    variables = MDApp.get_running_app().action_variables

    headers = {
        "Host": "www.pathofexile.com",
        "Connection": "keep - alive",
        "Content-Length": "127",
        "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="99", "Google Chrome";v="99"',
        "Accept": "*/*",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua-mobile": "?0",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/99.0.4844.82 Safari/537.36",
        "sec-ch-ua-platform": '"Windows"',
        "Origin": "https://www.pathofexile.com",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": f"https://www.pathofexile.com/trade/exchange/{variables['league']}",
        "Accept-Encoding": "gzip,deflate,br",
        "Accept-Language": "q=0.9,en-US;q=0.8,en;q=0.7",
        "Cookie": f"POESESSID={variables['POESESSID']}"
    }

    # Ссылка для запроса к странице с балком
    url = fr"https://www.pathofexile.com/api/trade/exchange/{variables['league']}"

    requests_interval = 0
    for item_i_want in items_i_want:
        simple_item = isinstance(item_i_want, str)
        for item_i_have in items_i_have:
            # Перерыв зависит от ответа АПИ ПОЕ
            time.sleep(requests_interval)

            # Запрос поиска
            data = {
                "query": {
                    "status": {
                        "option": "online"
                    },
                    "want": [item_i_want if simple_item else item_i_want['item'], ],
                    "have": [item_i_have, ],
                    "minimum": min_stock

                },
                "sort": {
                    "have": "asc"
                },
                "engine": "new"
            }

            # Получаем результат поиска по запросу
            # Если не работает, значит не установлен pip install brotli
            response_request = requests.post(url, headers=headers, json=data)
            response = response_request.json()

            interval_rule = response_request.headers['X-Rate-Limit-Ip'].split(",")[-1].split(":")
            requests_interval = float(interval_rule[1]) / float(interval_rule[0]) + .5

            try:
                # Код ошибки "Лимит запросов за промежуток времени (меняется динамически)"
                if response['error']['code'] == 3:
                    while response['error']['code'] == 3:
                        time.sleep(
                            float(response_request.headers['Retry-After']))  # Время "блокировки" при нарушении частоты
                        response_request = requests.post(url, headers=headers, json=data)
                        response = response_request.json()
            except Exception:
                pass

            results = response["result"]

            for deal_id, deal_info in results.items():
                deal = {
                    'id': deal_id,
                    'account_name': deal_info['listing']['account']['name'],
                    'character_name': deal_info['listing']['account']['lastCharacterName'],
                    'exchange_currency': deal_info['listing']['offers'][0]['exchange']['currency'],
                    'exchange_amount': deal_info['listing']['offers'][0]['exchange']['amount'],
                    'exchange_whisper': deal_info['listing']['offers'][0]['exchange']['whisper'],
                    'item_currency': deal_info['listing']['offers'][0]['item']['currency'],
                    'item_amount': deal_info['listing']['offers'][0]['item']['amount'],
                    'item_stock': deal_info['listing']['offers'][0]['item']['stock'],
                    'item_whisper': deal_info['listing']['offers'][0]['item']['whisper'],
                    'whisper': deal_info['listing']['whisper']
                }

                deal.update({'c_price': deal['exchange_amount'] / deal['item_amount'] * (
                    variables['divine_price'] if deal['exchange_currency'] == 'divine' else 1)})
                deal.update({'available_item_stock':
                                 math.floor(deal['item_stock'] / deal['item_amount']) * deal['item_amount']})
                if not simple_item:
                    deal.update({'profit': math.floor(
                        (item_i_want['bulk_price'] - deal['c_price']) * deal['available_item_stock'])})
                    deal.update({'max_qty': item_i_want['max_qty']})
                    deal.update({'image': item_i_want['image']})

                if simple_item or deal['c_price'] <= item_i_want['max_price']:
                    deals.append(deal)

    deals = sorted(deals,
        key=lambda d: d['profit'] if d.get('profit') else deal['exchange_amount'] / deal['item_amount'], reverse=True)

    return deals[:qty_deals]


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
