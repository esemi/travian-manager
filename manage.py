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
from selenium.common.exceptions import NoSuchElementException


RESOURCE_WOOD = 1
RESOURCE_FOOD = 2
RESOURCE_IRON = 3
RESOURCE_CLAY = 4
RESOURCE_FOOD_FREE = 5


class Manager(object):

    RUN_TIMEOUT = 5 * 60
    REQUEST_TIMEOUT = 20
    FIND_TIMEOUT = 5
    HOST = 'http://ts1.travian.ru'
    RESOURCE_PAGE = HOST + '/dorf1.php'
    HERO_PAGE = HOST + '/hero.php'
    HERO_ADVENTURE_PAGE = HOST + '/hero.php?t=3'

    is_logged = False

    VILLAGE_RESOURCE_BUILDINGS = []
    VILLAGE_RESOURCE_PRODUCTION = {}
    VILLAGE_RESOURCE_STOCK = {}
    VILLAGE_BUILD_QUEUE_SLOTS = 0
    VILLAGE_BUILD_QUEUE_SLOTS_LIMIT = 1

    HERO_HP_PERCENT = 0
    HERO_HP_PERCENT_THRESHOLD = 90

    RESOURCE_FOOD_FREE_THRESHOLD = 5

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
        self._login()
        if not self.is_logged:
            logging.error('login error')
            return

        while True:
            # анализируем деревню
            self._analyze()

            # строим здания
            self._improve_buildings()

            # отправляем героя в приключения
            self._send_hero_to_adventures()

            # todo застраиваем центр
            # todo нотифаим если идёт атака
            # todo прокачиваем героя
            # todo выполняем задания и забираем награды за них
            # todo separate action log
            # todo screenshots for timelapse

            sleep_time = self.RUN_TIMEOUT * 2 * random.random()
            logging.info('sleep random time %f', sleep_time)
            time.sleep(sleep_time)

    def _login(self):
        logging.info('login call')
        try:
            self.driver.get(self.HOST)
            login_form = self.driver.find_element_by_name("login")
            login_form.find_element_by_name('name').send_keys(self.user)
            login_form.find_element_by_name('password').send_keys(self.passwd)
            login_form.submit()

            self.driver.find_element_by_id('village_map')
            self.is_logged = True
            logging.info('login success')
        except:
            logging.info('login not success')
        
    def _analyze(self):
        logging.info('analyze call')

        # analyze resource buildings
        self._analyze_resource_buildings()
        
        # analyze resource input
        self._analyze_resource_production()

        # analyze resource stock
        self._analyze_resource_stock()

        # analyze buildings queue
        self._analyze_buildings_queue()

        # analyze hero
        self._analyze_hero()

    def _analyze_resource_buildings(self):
        result_builds = self._get_resource_buildings()
        logging.info('found %d resource buildings', len(result_builds))
        logging.debug(result_builds)
        self.VILLAGE_RESOURCE_BUILDINGS = result_builds

    def _analyze_resource_production(self):
        self.driver.get(self.RESOURCE_PAGE)
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

    def _analyze_resource_stock(self):
        self.driver.get(self.RESOURCE_PAGE)
        stock_list = self.driver.find_element_by_id('stockBar')
        result_stock = {}
        for row in stock_list.find_elements_by_xpath('.//li[contains(@class, "stockBarButton")]'):
            title = str(row.find_element_by_tag_name('img').get_attribute('alt')).strip()
            value = str(row.find_element_by_xpath('.//span[@class="value"]').text).strip()
            value = int(re.findall(r'(\d+)', value)[0])
            logging.debug('stock %s %d', title, value)
            if 'Глина' in title:
                type = RESOURCE_CLAY
            elif 'Зерно' in title:
                type = RESOURCE_FOOD
            elif 'Древесина' in title:
                type = RESOURCE_WOOD
            elif 'Железо' in title:
                type = RESOURCE_IRON
            else:
                type = RESOURCE_FOOD_FREE
            result_stock[type] = value
        logging.info('resource stock %s', result_stock)
        self.VILLAGE_RESOURCE_STOCK = result_stock

    def _analyze_buildings_queue(self):
        self.driver.get(self.RESOURCE_PAGE)
        try:
            div = self.driver.find_element_by_class_name('buildingList')
            cnt = len(div.find_elements_by_class_name('buildDuration'))
        except NoSuchElementException:
            cnt = 0

        self.VILLAGE_BUILD_QUEUE_SLOTS = max(0, self.VILLAGE_BUILD_QUEUE_SLOTS_LIMIT - cnt)
        logging.info('build queue free slots %d', self.VILLAGE_BUILD_QUEUE_SLOTS)

    def _analyze_hero(self):
        self.driver.get(self.HERO_PAGE)
        status_div = self.driver.find_element_by_id('attributes')
        value = status_div.find_element_by_class_name('health')\
            .find_element_by_xpath('.//td[contains(@class, "current")]').text.strip()
        value = int(re.findall(r'(\d+)', str(value))[0])
        self.HERO_HP_PERCENT = max(100, value)
        logging.info('hero HP percent %d', self.HERO_HP_PERCENT)

    def _improve_buildings(self):
        logging.info('improve buildings call')
        if not self.VILLAGE_BUILD_QUEUE_SLOTS:
            logging.info('build queue is full')
            return

        # improve food resource only if free value is lower
        improve_resource_types = self.VILLAGE_RESOURCE_PRODUCTION.items()
        if self.VILLAGE_RESOURCE_STOCK[RESOURCE_FOOD_FREE] > self.RESOURCE_FOOD_FREE_THRESHOLD:
            logging.info('ignore food resource by free value %d', self.VILLAGE_RESOURCE_STOCK[RESOURCE_FOOD_FREE])
            improve_resource_types = [i for i in improve_resource_types if i[0] != RESOURCE_FOOD]

        # select minimal production resource type
        minimal_production_type = sorted(improve_resource_types, key=operator.itemgetter(1))[0][0]
        logging.info('select %d type of resource for improve production', minimal_production_type)

        # select minimal level resource build
        minimal_level_build = sorted([i for i in self.VILLAGE_RESOURCE_BUILDINGS
                                      if i['type'] == minimal_production_type],
                                     key=lambda x: x['level'])[0]
        logging.info('select %s build for improve', minimal_level_build)

        # improve build
        self.driver.get(minimal_level_build['href'])
        div = self.driver.find_element_by_id('build')
        try:
            button = div.find_element_by_xpath('.//button[@class="green build"]')
            button.click()
            logging.info('upgrade building')
        except NoSuchElementException:
            logging.info('upgrade button not available')

    def _send_hero_to_adventures(self):
        logging.info('send hero to adventure call')
        if not self.HERO_HP_PERCENT > self.HERO_HP_PERCENT_THRESHOLD:
            logging.info('hero hp is smaller than threshold %s', self.HERO_HP_PERCENT)
            return

        self.driver.get(self.HERO_ADVENTURE_PAGE)
        adventure_list = self.driver.find_element_by_id('adventureListForm')
        links = adventure_list.find_elements_by_xpath('.//a[@class="gotoAdventure arrow"]')
        logging.info('find %d available adventures', len(links))

        if links:
            links[0].click()
            logging.info('send to adventure success')

    def _get_resource_buildings(self):
        self.driver.get(self.RESOURCE_PAGE)
        map_content = self.driver.find_element_by_id('rx')
        builds = map_content.find_elements_by_tag_name('area')
        result_builds = []
        for b in builds:
            b_desc = str(b.get_attribute('alt'))
            logging.debug('analyze resource build %s', b_desc)
            if not 'Уровень' in b_desc:
                continue
            b_href = str(b.get_attribute('href'))
            b_id = re.findall(r'id=(\d+)', b_href)[0]
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
                'href': b_href
            })
        return result_builds


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
            # todo save screenshot
        finally:
            m.close()


