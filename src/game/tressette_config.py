
import json


with open('config/tressette_game_config.json', 'r') as file:
    config = json.load(file)

with open('config/inventory_shop_config.json', 'r') as file:
    inventory_shop_config = json.load(file)
        
def get_price_change_name(num_change_name: int) -> int:
        if num_change_name == 0:
            return 1
        elif num_change_name == 1:
            return 2
        elif num_change_name == 2:
            return 5
        elif num_change_name == 3:
            return 10
        else:
            return 20
