if __name__ == "__main__":
    try:
        import time
        import traceback
        from common import abs_path_near_exe

        from main import ControlPanelApp
        ControlPanelApp().run()

    except Exception as e:
        error_text = str(e) + '\n' + traceback.format_exc()
        try:
            with open(abs_path_near_exe("error.txt"), 'w') as file:
                file.write(error_text)
        except:
            print(error_text)
            time.sleep(20)
