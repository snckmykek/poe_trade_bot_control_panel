import os
import requests

from kivy.animation import Animation
from kivy.lang import Builder
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ListProperty, OptionProperty, \
    ObjectProperty
from kivy.uix.behaviors import ToggleButtonBehavior
from kivy.uix.image import AsyncImage
from kivymd.app import MDApp
from kivymd.uix.behaviors.ripple_behavior import CommonRipple
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRectangleFlatIconButton, MDRectangleFlatButton, MDFlatButton
from kivymd.uix.list import OneLineIconListItem
from kivymd.uix.snackbar import Snackbar


from bots.common import CustomDialog, text_is_correct

app = MDApp.get_running_app()
Builder.load_file(os.path.abspath(os.path.join(os.path.dirname(__file__), "additional_functional.kv")))


class Content(MDBoxLayout):
    pass


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

        items = [(item.item,
                  item.ids.use.active,
                  float(item.ids.max_price.text) if item.ids.max_price.text else item.max_price,
                  float(item.ids.bulk_price.text) if item.ids.bulk_price.text else item.bulk_price,
                  int(item.ids.qty.text) if item.ids.qty.text else item.qty,
                  )
                 for item in self.ids.items_box.children]

        if items:
            app.bot.db.save_items(items)

        self.dialog_parent.dismiss()

    def refresh(self, *args):
        self.ids.items_box.clear_widgets()
        self.upload_items()

    def upload_items(self, items=None):
        for item_setting in app.bot.db.get_items(items):
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
                    icon='refresh',
                    text="Обновить с сайта ПОЕ",
                    theme_text_color="Custom",
                    text_color=app.theme_cls.primary_color,
                ),
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
        dialog.buttons[0].bind(on_release=lambda *_: dialog.content_cls.reload_categories())
        dialog.buttons[0].bind(on_release=lambda *_: update_poe_items())
        dialog.buttons[1].bind(on_release=dialog.dismiss)
        dialog.buttons[2].bind(on_release=dialog.content_cls.save)
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
        self.reload_categories()

    def reload_categories(self):
        self.categories = [
            {
                'text': category['category'],
                'func': self.change_current_category,
                'group': 'categories'
            } for category in app.bot.db.get_categories()
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

        for item_setting in app.bot.db.get_poe_items(self.current_category, search):
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
        "Cookie": f"POESESSID={MDApp.get_running_app().bot.v('trade_POESESSID')}"
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
                (category['label'], item['id'], item_name_from_text(item['text']), item.get('image', "")))

    app.bot.db.save_poe_items(items)


def item_name_from_text(text):
    """
    К названию карт прибавлен их уровень в скобочках - убираем. Cortex (Tier 10) -> Cortex.
    Остальное останется без изменений
    """
    return text.split(' (')[0]


class BuyerDealListItem(OneLineIconListItem):
    item = StringProperty()
    currency = StringProperty()
    image = StringProperty()
    item_min_qty = NumericProperty()
    currency_min_qty = NumericProperty()
    item_stock = NumericProperty()
    profit = NumericProperty()


class OneLineQueue(OneLineIconListItem):
    index = NumericProperty(0)
    left_widget_source = StringProperty("")
    status = OptionProperty('queue', options=['queue', 'progress', 'completed', 'error'])
    widgets = {
        'queue': 'sleep',
        'progress': 'play-circle-outline',
        'completed': 'check',
        'error': 'close-circle'
    }


class Blacklist(MDBoxLayout):
    title = "Черный список"
    dialog_parent = ObjectProperty()
    buttons = []

    def __init__(self, **kwargs):
        super(Blacklist, self).__init__(**kwargs)

        global app
        app = MDApp.get_running_app()

        self.buttons = [
            {
                'text': "Закрыть",
                'icon': 'window-close',
                'on_release': self.close
            },
        ]

    def on_pre_open(self, *args):
        self.load_blacklist()

    def close(self, *args):
        self.dialog_parent.dismiss()

    def load_blacklist(self):
        self.ids.container.clear_widgets()
        for character_name in MDApp.get_running_app().bot.db.get_blacklist():
            element = OneLineIconListItem(text=character_name)
            self.ids.container.add_widget(
                element
            )


class PriceChecker(MDBoxLayout):
    title = "Прайс чеккер"
    dialog_parent = ObjectProperty()
    buttons = []

    def __init__(self, **kwargs):
        super(PriceChecker, self).__init__(**kwargs)

        global app
        app = MDApp.get_running_app()

        self.buttons = [
            {
                'text': "Подобрать",
                'icon': 'find-replace',
                'on_release': self.open_item_selector
            },
            {
                'text': "Обновить все (каждый итем по времени = 22с/кол-во прокси)",
                'icon': 'window-close',
                'on_release': self.update_all
            },
            {
                'text': "Закрыть",
                'icon': 'window-close',
                'on_release': self.close
            },

        ]

    def close(self, *args):
        self.dialog_parent.dismiss()

    def update_all(self):
        pass

    def open_item_selector(self, *args):
        dialog = CustomDialog(
            auto_dismiss=False,
            title="Подбор предметов",
            type="custom",
            content_cls=ItemSelector(),
            buttons=[
                MDRectangleFlatIconButton(
                    icon='refresh',
                    text="Обновить с сайта ПОЕ",
                    theme_text_color="Custom",
                    text_color=app.theme_cls.primary_color,
                ),
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
        dialog.buttons[0].bind(on_release=lambda *_: dialog.content_cls.reload_categories())
        dialog.buttons[0].bind(on_release=lambda *_: update_poe_items())
        dialog.buttons[1].bind(on_release=dialog.dismiss)
        dialog.buttons[2].bind(on_release=dialog.content_cls.save)
        dialog.bind(on_pre_open=dialog.content_cls.on_pre_open)
        dialog.open()
