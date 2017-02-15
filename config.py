# -*- coding: utf-8 -*-

import os

CHROME_DRIVER_PATH = os.path.sep.join([os.path.abspath(os.path.dirname(__file__)), 'chromedriver'])
FIND_TIMEOUT = 10
REQUEST_TIMEOUT = 35
CUSTOM_WAIT_TIMEOUT = 10
LOOP_TIMEOUT = 15 * 60  # fact loop timeout maybe from LOOP_TIMEOUT to LOOP_TIMEOUT*2 (random use)

CREDS = ('login', 'pass')
HOST = 'http://ts1.travian.com'

HERO_HP_THRESHOLD_FOR_ADVENTURE = 60


HERO_ON_HOME_PATTERN = 'Hero is currently in village'
HERO_HP_THRESHOLD_FOR_TERROR = 75
HERO_TERROR_MIN_ENEMIES_STRENGTH = 4000
HERO_TERROR_MAX_ENEMIES_STRENGTH = 12000
HERO_TERROR_ESCORT_UNIT = 't2'
HERO_TERROR_ESCORT_COUNT = 300
NATURE_ENEMIES_STRENGTH = {
    'Rat': 45,
    'Spider': 75,
    'Snake': 100,
    'Bat': 116,
    'Wild Boars': 103,
    'Wolf': 150, 'Wolves': 150,
    'Bear': 340,
    'Crocodile': 620,
    'Tiger': 420,
    'Elephant': 960
}

SEND_FARMS_CANNON_FODDER_UNIT = 't2'
SEND_FARMS_CANNON_FODDER_COUNT = 50
SEND_FARMS_CANNON_FODDER_VILLAGE = 'village name'
SEND_FARMS_MIN_INTERVAL = 60 * 60 * 1  # 1 hour

FARM_LIST_SEND_BUTTON_PATTERN = 'start raid'
FARM_LIST_ADD_BUTTON_PATTERN = 'add'
FARM_LIST_CREATE_BUTTON_PATTERN = 'create'
FARM_LIST_BUILDING_PATTERN = 'Rally Point'
FARM_LIST_ATTACK_PATTERN1 = 'Won as attacker without losses'
FARM_LIST_ATTACK_PATTERN2 = 'with losses'
FARM_LIST_ATTACK_PATTERN3 = 'Lost as attacker'
FARM_LIST_TAB_PATTERN = 'Farm List'
FARM_LIST_ALREADY_ATTACK_PATTERN = 'Own attacking troops'
FARM_LIST_CARRY_FULL_PATTERN = 'carry full'
FARM_LIST_SEND_RESULT_PATTERN = 'raids have been made'
BARRACKS_BUILDING_PATTERN = 'Barracks'
STABLE_BUILDING_PATTERN = 'Stable'
SEND_ARMY_TAB_PATTERN = 'Send troops'
SEND_TROOPS_BUTTON_PATTERN = 'Send troops.'
REPORTS_ATTACK_PATTERN1 = 'Won as attacker without losses'
REPORTS_TODAY_PATTERN = 'today,'
REPORTS_TIME_PATTERN = r'today, (\d{2}):(\d{2})'

REPORTS_TROOPS_PATTERN = 'Troops'
REPORTS_CASUALTIES_PATTERN = 'Casualties'
REPORTS_PRISONERS_PATTERN = 'Prisoners'


AUTO_FARM_LISTS = ['farm list fullname']

AUTO_UPDATE_FARM_LISTS = [{
    'center_x': 10,
    'center_y': 20,
    'list_name': 'farm_list_fullname_example',
    'ignore_npc': False,
    'only_npc': True,
    'inh': {'max': 60, 'min': 16},
    'troop_id': 't4',
    'troop_count': 10
},]

AUTO_TROOP_BUILD = {
    'village_name': [
        {'troop_id': 't4', 'troop_queue_max': 20, 'troop_max': 600},
        {'troop_id': 't3', 'troop_queue_max': 20, 'troop_max': 1000},
    ]
}


IGNORE_FARM_PLAYERS = ['nikname1',]
IGNORE_FARM_ALLY = ['allyname1',]

AUCTION_BIDS = {
    'Ointment': 12,
    'Cage': 12,
    'Bucket': 210,
    'Bandage': 11,
    'Small Bandage': 11,
    'Scroll': 11,
}

SEND_FARMS_FACTOR = 1
UPDATE_FARM_LIST_FACTOR = 10
CLEAR_FARM_LIST_FACTOR = 45

ENABLE_HERO_TERROR = True
ENABLE_TRADE = True
ENABLE_SEND_FARMS = True
ENABLE_SEND_CANNON_RUBBER_FARMS = False
ENABLE_UPDATE_FARMS = True
ENABLE_CLEAR_FARMS = False
ENABLE_ADVENTURES = True
ENABLE_QUEST_COMPLETE = True
ENABLE_ATTACK_NOTIFY = True
ENABLE_REMOVE_FARM_REPORTS = True
ENABLE_BUILD_TROOPS = True

DEBUG = False


SMS_TO_PHONE = '+3123456789'
SMS_USER = 'smsc username'
SMS_PASS = 'smsc login'


try:
    from config_local import *
except ImportError:
    pass

