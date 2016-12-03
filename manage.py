#! /usr/bin/env python
# -*- coding: utf-8 -*-

import operator
import sys
import re
import logging
import time
import random

from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

RESOURCE_WOOD = 1
RESOURCE_FOOD = 2
RESOURCE_IRON = 3
RESOURCE_CLAY = 4


class Manager(object):

    RUN_TIMEOUT = 5 * 60
    REQUEST_TIMEOUT = 20
    FIND_TIMEOUT = 5
    HOST = 'http://ts1.travian.ru'
    is_logged = False
    VILLAGE_RESOURCE_BUILDINGS = []
    VILLAGE_RESOURCE_PRODUCTION = {}
    VILLAGE_BUILD_QUEUE_SLOTS = 0
    VILLAGE_BUILD_QUEUE_SLOTS_LIMIT = 1

    def __init__(self, user, passwd):
        self.user = user
        self.passwd = passwd
        firefox_capabilities = DesiredCapabilities.FIREFOX
        firefox_capabilities['marionette'] = True
        firefox_capabilities['binary'] = '/usr/bin/firefox'
        self.driver = webdriver.Firefox(capabilities=firefox_capabilities, timeout=self.REQUEST_TIMEOUT)
        self.driver.implicitly_wait(self.FIND_TIMEOUT)

    def close(self):
        if self.driver:
            self.driver.quit()

    def run(self):
        self.login()
        if not self.is_logged:
            logging.error('login error')
            return

        while True:
            # анализируем деревню
            self.analyze()

            # строим здания
            self.improve_buildings()

            # todo застраиваем центр
            # todo нотифаим если идёт атака
            # todo отправляем героя в приключения
            # todo прокачиваем героя
            # todo выполняем задания и забираем награды за них

            sleep_time = self.RUN_TIMEOUT * 2 * random.random()
            logging.info('sleep random time %f', sleep_time)
            time.sleep(sleep_time)

    def login(self):
        logging.info('login call')
        try:
            self.driver.get(self.HOST)
            login_form = self.driver.find_element_by_name("login")
            login_form.find_element_by_name('name').send_keys(self.user)
            login_form.find_element_by_name('password').send_keys(self.passwd)
            login_form.submit()

            village_map_element = self.driver.find_element_by_id('village_map')
            self.is_logged = True
            logging.info('login success %s' % village_map_element)
        except:
            logging.info('login not success')
        
    def analyze(self):
        logging.info('analyze call')

        # analyze resource buildings
        self._analyze_resource_buildings()
        
        # analyze resource input
        self._analyze_resource_production()

        # analyze buildings queue
        self._analyze_buildings_queue()

    def _analyze_resource_buildings(self):
        self.driver.get(self.HOST + '/dorf1.php')
        map_content = self.driver.find_element_by_id('rx')
        builds = map_content.find_elements_by_tag_name('area')
        result_builds = []
        for b in builds:
            b_desc = str(b.get_attribute('alt'))
            logging.debug('analyze resource build %s', b_desc)
            if not 'Уровень' in b_desc:
                continue

            b_id = re.findall(r'id=(\d+)', str(b.get_attribute('href')))[0]
            b_level = re.findall(r'Уровень (\d+)', str(b_desc))[0]
            b_type = None
            if 'Лесопилка' in b_desc:
                b_type = RESOURCE_WOOD
            elif 'Ферма' in b_desc:
                b_type = RESOURCE_FOOD
            elif 'Железный' in b_desc:
                b_type = RESOURCE_IRON
            elif 'Глиняный' in b_desc:
                b_type = RESOURCE_CLAY

            result_builds.append({
                'id': int(b_id),
                'desc': b_desc,
                'type': b_type,
                'level': int(b_level),
                'obj': b
            })
        logging.info('found %d resource buildings', len(result_builds))
        logging.debug(result_builds)
        self.VILLAGE_RESOURCE_BUILDINGS = result_builds

    def _analyze_resource_production(self):
        self.driver.get(self.HOST + '/dorf1.php')
        table = self.driver.find_element_by_id('production')
        result_production = {}
        for row in table.find_elements_by_tag_name('tr')[1:]:
            title = str(row.find_element_by_class_name('res').text)
            value = str(row.find_element_by_class_name('num').text).strip()
            value = int(re.findall(r'(\d+)', value)[0])
            logging.debug('production %s %d', title, value)
            type = None
            if 'Глина' in title:
                type = RESOURCE_CLAY
            elif 'Зерно' in title:
                type = RESOURCE_FOOD
            elif 'Древесина' in title:
                type = RESOURCE_WOOD
            elif 'Железо' in title:
                type = RESOURCE_IRON
            result_production[type] = value
        logging.info('resource production %s', result_production)
        self.VILLAGE_RESOURCE_PRODUCTION = result_production

    def _analyze_buildings_queue(self):
        self.driver.get(self.HOST + '/dorf1.php')
        try:
            div = self.driver.find_element_by_class_name('buildingList')
            cnt = len(div.find_elements_by_class_name('buildDuration'))
        except:
            cnt = 0

        self.VILLAGE_BUILD_QUEUE_SLOTS = max(0, self.VILLAGE_BUILD_QUEUE_SLOTS_LIMIT - cnt)
        logging.info('build queue free slots %d', self.VILLAGE_BUILD_QUEUE_SLOTS)

    def improve_buildings(self):
        logging.info('improve buildings call')
        if not self.VILLAGE_BUILD_QUEUE_SLOTS:
            logging.info('build queue is full')
            return

        # select minimal production resource type
        minimal_production_type = sorted(self.VILLAGE_RESOURCE_PRODUCTION.items(),
                                         key=operator.itemgetter(1))[0][0]
        logging.info('select %d type of resource for improve production', minimal_production_type)

        # select minimal level resource build
        minimal_level_build = sorted([i for i in self.VILLAGE_RESOURCE_BUILDINGS
                                      if i['type'] == minimal_production_type],
                                     key=lambda x: x['level'])[0]
        logging.info('select %s build for improve', minimal_level_build)

        # improve build

    



if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        username = sys.argv[1]
        passwd = sys.argv[2]
    except IndexError:
        logging.warning('usage python3 manage.py %username% %passwd%')
    else:
        logging.info('run %s %s' % (username, passwd))
        m = Manager(username, passwd)
        try:
            m.run()
        except Exception as e:
            logging.error('exception %s', e)
        finally:
            m.close()


