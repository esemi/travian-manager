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

try:
    from config_local import *
except ImportError:
    pass

