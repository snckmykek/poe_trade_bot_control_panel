import math
import os
from os.path import dirname

import cv2
import numpy as np
import pytesseract
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


# region Картинка в число
def clear_noise(thresh_original):
    thresh = cv2.bitwise_not(thresh_original)

    # ищем контуры и складируем их в переменную contours
    contours, hierarchy = cv2.findContours(thresh.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    new = np.zeros([*thresh.shape[:2], 1], dtype=np.uint8)

    contours = list(filter(lambda c: c.shape[0] < thresh.shape[0] / 3, contours))

    # отображаем контуры поверх изображения
    for i in range(len(contours)):
        cv2.drawContours(new, contours, i, 255, thickness=cv2.FILLED)

    for y in range(new.shape[0]):
        for x in range(new.shape[1]):
            if new[y][x] == 255:
                thresh_original[y][x] = 255


def image_to_int(image, chan):
    # TODO Изменить расчет x_slice, y_slice
    # TODO Расчет занимает в среднем 0.35 сек и состоит из 3 частей: обрезание картинки (0.07с),
    #  удаление контуров меньше трети высоты картинки (0.08с), нейронка распознавания числа (0.2с)
    #  оптимизировать можно только первые 2 пункта, но нужно ли? 99% случаев обработать нужно будет 1-2 картинки
    # cv2.imshow('original5', image)
    # cv2.waitKey(0)
    # cv2.destroyAllWindows()

    # Конвертируем в черно-белый
    image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

    try:  # Пытаемся обрезать по цифре, но при неудаче просто пропускаем этот этап
        points_x = []
        points_y = []

        x_start = -1
        y_start = -1

        for y in range(image.shape[0]):
            for x in range(image.shape[1]):
                if image[y][-1 - x] == 0:
                    points_x.append(image.shape[1] - x)

                    if y_start == -1:
                        y_start = y
                    break

        for x in range(image.shape[1]):
            for y in range(image.shape[0]):
                if image[-1 - y][x] == 0:
                    points_y.append(image.shape[0] - y)

                    if x_start == -1:
                        x_start = x
                    break

        points_x = sorted(points_x, reverse=True)
        while True:
            if points_x[0] - points_x[1] > 1:
                points_x.pop(0)
            else:
                break

        points_y = sorted(points_y, reverse=True)
        while True:
            if points_y[0] - points_y[1] > 1:
                points_y.pop(0)
            else:
                break

        x_slice = math.ceil(sum(points_x) / len(points_x))
        y_slice = math.ceil(sum(points_y) / len(points_y))

        sliced = image[y_start: y_slice, x_start: x_slice]

        image = np.zeros([sliced.shape[0] + 2, sliced.shape[1] + 2, 1], np.uint8)

        for y in range(sliced.shape[0]):
            for x in range(sliced.shape[1]):
                image[y + 1][x + 1] = sliced[y][x]

    except Exception as e:
        print(e)

    # Изменяем размер изображения, чтобы нейронке лучше понималось
    scale_percent = 25 / image.shape[0]
    width = int(image.shape[1] * scale_percent)
    height = int(image.shape[0] * scale_percent)
    dim = (width, height)
    image = cv2.resize(image, dim, interpolation=cv2.INTER_CUBIC)

    # Отделяем цифры (вместе с мусором) по яркости белого
    _, threshold_image = cv2.threshold(image, chan, 255, 1, cv2.THRESH_BINARY)

    # Удаляем мусор (контуры меньше трети высоты картинки - это не цифры)
    clear_noise(threshold_image)

    threshold_image = cv2.resize(threshold_image, [dim[0] * 2, dim[1] * 2], interpolation=cv2.INTER_CUBIC)

    result = pytesseract.image_to_string(
        threshold_image, config='--psm 10 --oem  3 -c tessedit_char_whitelist=0123456789')
    result = result.replace("\n", "")

    try:
        return int(result)
    except ValueError:
        return 0
# endregion
