import threading
import time
import keyboard

PRINT_KEY_INFO = False
PRINT_HOTKEY = False


class HotkeyController:
    _pressed_keys: set = set()
    _hotkeys_functions: dict = dict()
    _sorted_hotkeys: list = []

    def __init__(self):
        keyboard.hook(self.on_key_state)

    def on_key_state(self, key):
        if PRINT_KEY_INFO:
            print(key.__dict__)

        scan_code = key.scan_code

        if key.event_type == 'down':
            if scan_code in self._pressed_keys:
                return

            self._pressed_keys.add(scan_code)
            self._handle_hotkey()
        else:
            try:
                self._pressed_keys.remove(scan_code)
            except KeyError:
                pass

    def _handle_hotkey(self):
        for hotkey in self._sorted_hotkeys:
            if self._hotkey_is_pressed(hotkey):
                self._hotkeys_functions[hotkey]()
                return

    def _hotkey_is_pressed(self, hotkey):
        if not set(list(hotkey)) - self._pressed_keys:
            if PRINT_HOTKEY:
                print(hotkey)
            return True
        else:
            return False

    def add_hotkey(self, hotkey, func):
        hotkey_keys = self.get_hotkey_keys(hotkey)
        self._hotkeys_functions.update({tuple(set(hotkey_keys)): func})
        self._sorted_hotkeys = sorted(self._hotkeys_functions.keys(), key=len, reverse=True)

    def remove_hotkey(self, hotkey):
        hotkey_keys = self.get_hotkey_keys(hotkey)
        try:
            self._hotkeys_functions.pop(tuple(set(hotkey_keys)))
            self._sorted_hotkeys = sorted(self._hotkeys_functions.keys(), key=len, reverse=True)
        except KeyError:
            pass

    @staticmethod
    def get_hotkey_keys(hotkey):
        parsed = keyboard.parse_hotkey(hotkey)
        if len(parsed) != 1:
            raise ValueError("Хоткей должен состоять из одного или нескольких символов, разделенных знаком +")
        return [step[0] for step in parsed[0]]


# class MouseController:
#     _control_queue: list = []
#     _current_owner: str
#     _default_owner: str = ""
#     _call_owner: str = ""
#
#     def __call__(self, owner):
#         self._call_owner = owner
#
#     def __enter__(self):
#         self.take_control(self._call_owner)
#
#     def __exit__(self, exception_type, exception_val, trace):
#         self.release_control()
#         return True
#
#     def take_control(self, owner):
#
#         if owner in self._control_queue:
#             print(f"Нарушена последовательность работы контроля. Для '{owner}' уже получен контроль.")
#             return
#
#         self._append_owner_to_queue(owner)
#         self._wait_owners_turn(owner)
#         self._transfer_control_to(owner)
#
#     def _append_owner_to_queue(self, owner):
#         self._control_queue.append(owner)
#
#     def _wait_owners_turn(self, owner):
#         while owner != self._control_queue[0]:
#             time.sleep(.5)
#
#     def _transfer_control_to(self, new_owner):
#         self._current_owner = new_owner
#
#     def release_control(self):
#
#         try:
#             self._remove_owner_from_queue(self._current_owner)
#             self._transfer_control_to(self._default_owner)
#         except ValueError:
#             print(f"Нарушена последовательность работы контроля. У '{self._current_owner}' "
#                   f"нет контроля на данный момент.")
#
#     def _remove_owner_from_queue(self, owner):
#         self._control_queue.remove(self._current_owner)
#
#     def reset_control_queue(self):
#         self._control_queue.clear()


hotkey_controller = HotkeyController()
mouse_controller = threading.Lock()

if __name__ == '__main__':
    # PRINT_KEY_INFO = True
    hotkey_controller.add_hotkey('alt+f11', lambda: print('alt+f11'))
    hotkey_controller.add_hotkey('f11', lambda: print('f11'))
    hotkey_controller.add_hotkey('ctrl+alt+f11', lambda: print('ctrl+alt+f11'))
    keyboard.wait()
