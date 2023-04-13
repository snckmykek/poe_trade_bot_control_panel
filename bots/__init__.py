from bots.example import Bot as ExampleBot
from bots.poe.buyer import Bot as PoeBuyerBot
# from bots.poe.tujen import Bot as PoeTujenBot
# from bots.poe.craft import Bot as PoeCraftBot
from bots.poe.elder import Bot as PoeElder
from bots.poe.seller import Bot as PoeSeller

bots_list = [
    ExampleBot,
    PoeBuyerBot,
    PoeSeller,
    # PoeTujenBot,
    # PoeCraftBot,
    PoeElder,
]
