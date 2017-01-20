# -*- coding: utf-8 -*-

import os

CHROME_DRIVER_PATH = os.path.sep.join([os.path.abspath(os.path.dirname(__file__)), 'chromedriver'])
FIND_TIMEOUT = 15
REQUEST_TIMEOUT = 45
CUSTOM_WAIT_TIMEOUT = 15
LOOP_TIMEOUT = 11 * 60  # fact loop timeout maybe from LOOP_TIMEOUT to LOOP_TIMEOUT*2 (random use)

CREDS = ('login', 'pass')
HOST = 'http://ts1.travian.com'

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

HERO_ON_HOME_PATTERN = 'Hero is currently in village'

HERO_HP_THRESHOLD_FOR_ADVENTURE = 65
HERO_HP_THRESHOLD_FOR_TERROR = 85
HERO_TERROR_MIN_ENEMIES = 20

FARM_LIST_SEND_BUTTON_PATTERN = 'Start raid'
FARM_LIST_BUILDING_PATTERN = 'Rally Point'
FARM_LIST_LOSSES_PATTERN1 = 'Lost as attacker'
FARM_LIST_LOSSES_PATTERN2 = 'with losses'
FARM_LIST_TAB_PATTERN = 'Farm List'
FARM_LIST_ALREADY_ATTACK_PATTERN = 'Own attacking troops'
FARM_LIST_SEND_RESULT_PATTERN = 'raids have been made'
SEND_ARMY_TAB_PATTERN = 'Send troops'
REPORTS_ATTACK_PATTERN1 = 'as attacker without losses'

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

AUCTION_BIDS = {
    'Ointment': 10,
    'Cage': 15,
    'Small Bandage': 5,
}

ENABLE_HERO_TERROR = True
ENABLE_SEND_FARMS = True
ENABLE_UPDATE_FARMS = True
ENABLE_TRADE = True
ENABLE_ADVENTURES = True
ENABLE_QUEST_COMPLETE = True
ENABLE_ATTACK_NOTIFY = False
ENABLE_REMOVE_FARM_REPORTS = True


SMS_TO_PHONE = '+3123456789'
SMS_USER = 'smsc username'
SMS_PASS = 'smsc login'


def send_attack_notify(message):
    pass


try:
    from config_local import *
except ImportError:
    pass

