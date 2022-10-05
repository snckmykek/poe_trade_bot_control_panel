import os
import time

import cv2
import numpy as np
import pyautogui
import requests
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty, OptionProperty, \
    ObjectProperty
from kivy.uix.behaviors import ToggleButtonBehavior
from kivy.uix.image import AsyncImage
from kivymd.app import MDApp
from kivymd.uix.behaviors import RoundedRectangularElevationBehavior
from kivymd.uix.behaviors.ripple_behavior import CommonRipple
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRectangleFlatIconButton, MDRectangleFlatButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDIcon
from kivymd.uix.list import IconLeftWidget, OneLineIconListItem
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.textfield import MDTextField
import gv

"""
Добавить AsyncImage в ItemRow и имаге в базу данных, чтобы в ItemRow попадало
Добавить в .кв друга этого далбаёба ItemIconPOE чтобы ему прописать он_релиз
"""

app = MDApp.get_running_app()
Builder.load_file("additional_functional.kv")


class Items(MDBoxLayout):
    title = "Настройки цен"
    dialog_parent = ObjectProperty()
    buttons = []

    def __init__(self, **kwargs):
        super(Items, self).__init__(**kwargs)

        global app
        app = MDApp.get_running_app()

        self.buttons = [
            {
                'text': "Отменить",
                'icon': 'window-close',
                'on_release': self.cancel
            },
            {
                'text': "Обновить",
                'icon': 'refresh',
                'on_release': self.refresh
            },
            {
                'text': "Подобрать",
                'icon': 'find-replace',
                'on_release': self.open_item_selector
            },
            {
                'text': "Сохранить",
                'icon': 'check',
                'on_release': self.save
            },
        ]

    def on_pre_open(self, *args):
        self.refresh()

    def cancel(self, *args):
        self.dialog_parent.dismiss()

    def save(self, *args):
        def values_is_correct(item):
            return (text_is_correct(item.ids.max_price.text_type, item.ids.max_price.text)
                    and text_is_correct(item.ids.max_price.text_type, item.ids.bulk_price.text)
                    and text_is_correct(item.ids.max_price.text_type, item.ids.qty.text))

        errors = [item.name for item in self.ids.items_box.children if not values_is_correct(item)]

        if errors:
            Snackbar(text=f"Ошибочные значения у предметов: {','.join(errors)}").open()
            return

        items = [(app.type,
                  item.item,
                  item.ids.use.active,
                  int(item.ids.max_price.text) if item.ids.max_price.text else item.max_price,
                  int(item.ids.bulk_price.text) if item.ids.bulk_price.text else item.bulk_price,
                  int(item.ids.qty.text) if item.ids.qty.text else item.qty,
                  )
                 for item in self.ids.items_box.children]

        if items:
            gv.db.af_save_items(items)

        self.dialog_parent.dismiss()

    def refresh(self, *args):
        self.ids.items_box.clear_widgets()
        self.upload_items()

    def upload_items(self, items=None):
        for item_setting in gv.db.af_get_items(app.type, items):
            self.ids.items_box.add_widget(
                ItemRow(
                    name=item_setting['name'],
                    item=item_setting['item'],
                    image=item_setting['image'],
                    icon_func=self.delete_row,
                    bulk_price=item_setting['bulk_price'],
                    max_price=item_setting['max_price'],
                    qty=item_setting['max_qty'],
                    use=item_setting['use'],
                )
            )

    def delete_row(self, row):
        self.ids.items_box.remove_widget(row)

    def set_use_all_items(self, value):
        for item in self.ids.items_box.children:
            item.use = value

    def open_item_selector(self, *args):
        dialog = CustomDialog(
            auto_dismiss=False,
            title="Подбор предметов",
            type="custom",
            content_cls=ItemSelector(),
            buttons=[
                MDRectangleFlatIconButton(
                    icon='close',
                    text="Отменить",
                    theme_text_color="Custom",
                    text_color=app.theme_cls.primary_color,
                ),
                MDRectangleFlatIconButton(
                    icon='content-save-outline',
                    text="Сохранить",
                    theme_text_color="Custom",
                    text_color=app.theme_cls.primary_color,
                ),
            ],
        )

        dialog.content_cls.dialog_parent = dialog
        dialog.content_cls.change_items_func = self.change_items
        dialog.content_cls.selected_items = [item.item for item in self.ids.items_box.children]
        dialog.buttons[0].bind(on_release=dialog.dismiss)
        dialog.buttons[1].bind(on_release=dialog.content_cls.save)
        dialog.bind(on_pre_open=dialog.content_cls.on_pre_open)
        dialog.open()

    def change_items(self, items):
        unchangeable_items = []
        removed_items_objects = []

        for item in self.ids.items_box.children:
            if item.item not in items:
                removed_items_objects.append(item)
            else:
                unchangeable_items.append(item.item)

        for item in removed_items_objects:
            self.ids.items_box.remove_widget(item)

        items_to_upload = list(set(items) - set(unchangeable_items))
        if items_to_upload:
            self.upload_items(items_to_upload)


class ItemSelector(MDBoxLayout):
    categories = ListProperty()
    change_items_func = ObjectProperty()
    current_category = StringProperty()
    dialog_parent = ObjectProperty()
    selected_items = ListProperty()
    _timer = NumericProperty(.0)
    _anim = Animation(_timer=0, d=_timer)

    def on_pre_open(self, *args):
        self.categories = [
            {
                'text': category['category'],
                'func': self.change_current_category,
                'group': 'categories'
            } for category in gv.db.af_get_categories()
        ]

    def change_current_category(self, instance):
        self.current_category = instance.text if instance.state == 'down' else ""
        self.upload_poe_items()

    def start_anim(self):
        self._anim.cancel(self)
        self._timer = .3
        self._anim = Animation(_timer=0, d=self._timer)
        self._anim.bind(on_complete=lambda *_: self.on_complete_anim())
        self._anim.start(self)

    def on_complete_anim(self):
        self.upload_poe_items()

    def upload_poe_items(self):

        search = self.ids.search.text

        items = self.ids['items']
        items.clear_widgets()

        if not self.current_category and not search:
            return

        for item_setting in gv.db.af_get_poe_items(self.current_category, search):
            if item_setting['image']:
                item = ItemIconPOE(
                    category=item_setting['category'],
                    image_path=item_setting['image'],
                    item=item_setting['item'],
                    name=item_setting['name'],
                    func=self.on_release_item,
                    state='down' if item_setting['item'] in self.selected_items else 'normal',
                )
            else:
                item = ItemLinePOE(
                    category=item_setting['category'],
                    image_path=item_setting['image'],
                    item=item_setting['item'],
                    name=item_setting['name'],
                    text=item_setting['name'],
                    func=self.on_release_item,
                    state='down' if item_setting['item'] in self.selected_items else 'normal',
                )

            items.add_widget(item)

    def save(self, *args):
        if self.change_items_func:
            self.change_items_func(self.selected_items)
        self.dialog_parent.dismiss()

    def on_release_item(self, instance):
        if instance.state == 'down':
            if instance.item not in self.selected_items:
                self.selected_items.append(instance.item)
        else:
            if instance.item in self.selected_items:
                self.selected_items.remove(instance.item)


class ItemRow(MDBoxLayout):
    bulk_price = NumericProperty(0)
    icon_func = ObjectProperty()
    name = StringProperty()
    item = StringProperty()
    max_price = NumericProperty(0)
    qty = NumericProperty(0)
    use = BooleanProperty(False)
    image = StringProperty()

    _click1 = False
    _point1 = (0, 0)
    _template_window_name = ""

    def __init__(self, **kwargs):
        super(ItemRow, self).__init__(**kwargs)

    def make_template(self):

        from win32api import GetSystemMetrics
        rect = [0, 0, GetSystemMetrics(0), GetSystemMetrics(1)]

        x = rect[0]
        y = rect[1]
        w = rect[2] - x
        h = rect[3] - y

        time.sleep(1)

        img_rgb = pyautogui.screenshot(region=[x, y, w, h])
        img = cv2.cvtColor(np.array(img_rgb), 2)
        self._click1 = False
        self._point1 = (0, 0)

        def click(event, click_x, click_y, flags, params):
            if event == cv2.EVENT_LBUTTONDOWN:
                self._click1 = True
                self._point1 = (click_x, click_y)
                if self._template_window_name:
                    cv2.destroyWindow(self._template_window_name)
            elif event == cv2.EVENT_MOUSEMOVE and self._click1:
                img_copy = img.copy()
                cv2.rectangle(img_copy, self._point1, (click_x, click_y), (0, 0, 255), 2)
                cv2.imshow("Image", img_copy)
            elif event == cv2.EVENT_LBUTTONUP:
                self._click1 = False
                sub_img = img[self._point1[1]:click_y, self._point1[0]:click_x]
                sub_img_size = sub_img.shape[-2::-1]
                self._template_window_name = f"Размер шаблона: {sub_img_size}"
                cv2.imshow(self._template_window_name, sub_img)
                cv2.resizeWindow(self._template_window_name, [max(150, sub_img_size[0]), max(150, sub_img_size[1])])

                setting = gv.db.get_settings(app.type, "setting_checkbox_window_resolution")
                if setting:
                    directory = os.path.join(app.type, setting[0]['value'], "items")
                else:
                    directory = os.path.join(app.type, "relative", "items")
                templates_path = os.path.join(r"images\templates", directory)

                if not os.path.exists(templates_path):
                    os.mkdir(templates_path)

                template_name = f"{self.item}.png"

                cv2.imwrite(os.path.join(templates_path, template_name),
                            img[self._point1[1]:click_y, self._point1[0]:click_x])

        cv2.namedWindow("Image")
        cv2.setMouseCallback("Image", click)
        cv2.imshow("Image", img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

        self.md_bg_color = [1, 0, 0, 0 if self.template_exists() else .25]

    def template_exists(self):
        setting = gv.db.get_settings(app.type, "setting_checkbox_window_resolution")
        if setting:
            directory = os.path.join(app.type, setting[0]['value'], "items")
        else:
            directory = os.path.join(app.type, "relative", "items")
        templates_path = os.path.join(r"images\templates", directory)

        return os.path.exists(os.path.join(templates_path, f"{self.item}.png"))


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


class Deals(MDBoxLayout):
    title = "Очередь сделок"
    dialog_parent = ObjectProperty()
    buttons = []

    def __init__(self, **kwargs):
        super(Deals, self).__init__(**kwargs)

        global app
        app = MDApp.get_running_app()

        self.buttons = [
            {
                'text': "Закрыть",
                'icon': 'window-close',
                'on_release': self.cancel
            },
        ]

    def on_pre_open(self, *args):
        pass

    def test(self):
        app.action_variables.update({'deals': [
            {'text': f"Сделка {i}"} for i in range(8)
        ]})

        app.action_variables.update({'current_deal': {
            'item': "1",
            'image': "/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lBZGRNb2RUb1JhcmUiLCJzY2FsZSI6MX1d/33f2656aea/CurrencyAddModToRare.png",
            'name': "nickname",
            'c_price': 55,
            'qty': 2,
            'bulk_price': 70,
            'profit': 30,
        }})

    def cancel(self, *args):
        self.dialog_parent.dismiss()


class ToggleRectangleFlatButton(MDRectangleFlatButton, ToggleButtonBehavior):
    func = ObjectProperty()
    size_hint_x = NumericProperty(1)

    def on_touch_down(self, touch):
        """
        Переписана функция (не запускает анимацию фона при нажатии), пропускает выполнение в родителе
        """

        if touch.is_mouse_scrolling:
            return False
        elif not self.collide_point(touch.x, touch.y):
            return False
        elif self in touch.ud:
            return False
        elif self.disabled:
            return False
        else:
            return super(CommonRipple, self).on_touch_down(touch)


class ItemIconPOE(ToggleButtonBehavior, AsyncImage):
    category = StringProperty()
    image_path = StringProperty()
    item = StringProperty()
    name = StringProperty()
    func = ObjectProperty()


class ItemLinePOE(ToggleRectangleFlatButton):
    category = StringProperty()
    image_path = StringProperty()
    item = StringProperty()
    name = StringProperty()


def update_poe_items():
    """
    Для настроек, выполняется(обновляются предметы ПОЕ) вручную по необходимости и сохраняется в БД.
    TODO: Продумать логичность автоматизирования
    """
    headers = {
        "Host": "www.pathofexile.com",
        "Connection": "keep - alive",
        "Accept": "*/*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/99.0.4844.82 Safari/537.36",
        "Origin": "https://www.pathofexile.com",
        "Accept-Encoding": "gzip,deflate,br",
        "Accept-Language": "q=0.9,en-US;q=0.8,en;q=0.7",
        "Cookie": f"POESESSID={MDApp.get_running_app().action_variables['POESESSID']}"
    }

    # Ссылка для запроса к странице с балком
    url = r"https://www.pathofexile.com/api/trade/data/static"

    # 1) Получаем результат поиска по запросу
    # Если не работает, значит не установлен pip install brotli
    response_request = requests.get(url, headers=headers)
    response = response_request.json()

    items = []

    for category in response['result']:
        for item in category['entries']:
            items.append(
                (category['label'], item['id'], item['text'], item['image'] if item.get('image') else ""))

    gv.db.af_save_poe_items(items)


class DealOneLineIconListItem(OneLineIconListItem):
    item_currency = StringProperty()
    exchange_currency = StringProperty()
    image = StringProperty()
    item_amount = NumericProperty()
    exchange_amount = NumericProperty()
    item_stock = NumericProperty()
    available_item_stock = NumericProperty()
    profit = NumericProperty()