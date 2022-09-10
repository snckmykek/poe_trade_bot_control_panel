import threading
import time
from kivymd.app import MDApp


def test(text):

    app = MDApp.get_running_app()

    i = 0
    while i < 5:
        if need_stop_action():
            return
        i += 1
        app.set_status(f"Выполняю: {i}", True)
        time.sleep(1)

    app.main.do_next_action()


def need_stop_action():
    app = MDApp.get_running_app()

    if app.need_stop_action:
        if app.need_pause:
            app.set_running(False)
            app.set_status(f"Остановлен вручную")
        else:
            app.set_status(f"Остановлен вручную", True)
        return True
    else:
        return False

