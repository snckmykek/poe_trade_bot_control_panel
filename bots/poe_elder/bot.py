from bots.bot import Bot, Simple, Template, Coord


class PoeElder(Bot):
    # Обязательные
    icon = 'account-arrow-left'
    name = "ПОЕ: Елдер"
    key = "poe_elder"

    # Кастомные

    def __init__(self):
        super(PoeElder, self).__init__()

        self.set_task_tab_buttons()
        self.set_tasks()
        self.set_windows()

    # region init
    def set_task_tab_buttons(self):
        self.task_tab_buttons = [
        ]

    def set_tasks(self):
        self.tasks = [
            {
                'name': "Подготовка",
                'timer': 40,
                'available_mode': 'always',
                'stages': [
                    {
                        'func': self.test,
                        'name': "Тест"
                    },
                ]
            },
        ]

    def set_variables_setting(self):
        self.variables_setting = {
            'Общие настройки': [
                Simple(
                    key='test',
                    name="Тест",
                    type='str'
                ),
            ],
            'Окно: Path of Exile (игра)': [
                Coord(
                    key='coord_currency_tab',
                    name="Координаты валютной вкладки",
                    relative=True,
                    type='coord',
                    window='poe'
                ),
                Template(
                    key='template_game_loaded',
                    name=
                    "Статичный кусок экрана, однозначно говорящий о загрузке локи (например, сиськи телки где мана)",
                    region=Coord(
                        key='region_game_loaded',
                        name="",
                        relative=True,
                        snap_mode='rb',
                        type='region',
                        window='poe'
                    ),
                    relative=True,
                    type='template',
                    window='poe'
                ),
            ]
        }

    def set_windows(self):
        self.windows = {
            'main': {'name': ""},
            'poe': {'name': "Path of Exile", 'expression': ('x', 'y', 'w', 'h')},
            'poe_except_inventory': {'name': "Path of Exile", 'expression': ('x', 'y', 'w - 0.6166 * h', 'h')}

        }

    def delayed_init(self, *_):
        self.set_variables_setting()

    # endregion

    def test(self):
        pass