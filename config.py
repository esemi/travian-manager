# -*- coding: utf-8 -*-

CREDS = ('login', 'pass')
HOST = 'http://ts1.travian.ru'

RESOURCE_WOOD = 1
RESOURCE_FOOD = 2
RESOURCE_IRON = 3
RESOURCE_CLAY = 4
RESOURCE_FOOD_FREE = 5

RESOURCE_CLAY_NAME = 'Clay'
RESOURCE_WOOD_NAME = 'Lumber'
RESOURCE_FOOD_NAME = 'Crop'
RESOURCE_IRON_NAME = 'Iron'

RESOURCE_WOOD_MINE = 'Woodcutter'
RESOURCE_IRON_MINE = 'Iron Mine'
RESOURCE_FOOD_MINE = 'Cropland'
RESOURCE_CLAY_MINE = 'Clay Pit'

RESOURCE_BUILD_PATTERN_LEVEL = 'Level'

BUILD_QUEUE_SLOTS_LIMIT = 2

HERO_HP_THRESHOLD_FOR_ADVENTURE = 80

FARM_LIST_SEND_BUTTON_PATTERN = 'Start raid'
FARM_LIST_BUILDING_PATTERN = 'Rally Point'
FARM_LIST_WON_PATTERN = 'without losses'
FARM_LIST_TAB_PATTERN = 'Farm List'
FARM_LIST_ALREADY_ATTACK_PATTERN = 'Own attacking troops'

AUTO_FARM_LISTS = ['farm list fullname']

AUTO_COLLECT_FARM_LISTS = [{
    'center_x': 10,
    'center_y': 20,
    'list_name': 'farm_list_fullname_example',
    'ignore_npc': False,
    'only_npc': True,
    'inh': {'max': 60, 'min': 16},
    'troop_id': 't4',
    'troop_count': 10
},]

IGNORE_FARM_PLAYERS = ['nikname1',]
IGNORE_FARM_ALLY = ['allyname1',]

ENABLE_SEND_FARMS = True
ENABLE_UPDATE_FARMS = True
ENABLE_TRADE = True
ENABLE_ADVENTURES = True
ENABLE_QUEST_COMPLETE = True

try:
    from config_local import *
except ImportError:
    pass

