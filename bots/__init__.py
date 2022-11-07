import os
import importlib.util as ilu

bots_list = []
with os.scandir('bots') as files:
    _service_packages = ['__pycache__', 'for_development']
    bots_dirs = [file.name for file in files if (file.is_dir() and file.name not in _service_packages)]
    for bot_dir in bots_dirs:
        spec = ilu.spec_from_file_location('__init__', f'bots/{bot_dir}/__init__.py')
        init_module = ilu.module_from_spec(spec)
        spec.loader.exec_module(init_module)

        bots_list.append(init_module.Bot)
