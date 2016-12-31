#! /usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import time
from json import loads
import os
import random
import re

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support.ui import Select

import config


def send_desktop_notify(message):
    os.system('notify-send "%s" "%s"' % ('travian-bot event', message))


class Manager(object):

    RUN_TIMEOUT = 10 * 60
    REQUEST_TIMEOUT = 20
    FIND_TIMEOUT = 5

    MAIN_PAGE = config.HOST + '/dorf1.php'
    VILLAGE_PAGE = config.HOST + '/dorf2.php'
    HERO_PAGE = config.HOST + '/hero.php'
    HERO_ADVENTURE_PAGE = config.HOST + '/hero.php?t=3'
    MAP_PAGE = config.HOST + '/karte.php'
    MAP_DATA_PAGE = config.HOST + '/ajax.php?cmd=mapPositionData'

    loop_number = 0
    is_logged = False
    resource_buildings = []
    resource_production = {}
    resource_stock = {}
    build_queue_slots = 0
    hero_hp = 0
    ajax_token = ''

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
            self.loop_number += 1
            self._sanitizing()

            # анализируем деревню
            self._analyze()

            if config.ENABLE_ADVENTURES:
                # отправляем героя в приключения
                self._send_hero_to_adventures()

            if config.ENABLE_QUEST_COMPLETE:
                # забираем награды за квесты
                self._quest_complete()

            if config.ENABLE_SEND_FARMS:
                # шлём пылесосы по фарм листам
                self._send_army_to_farm()

            if config.ENABLE_UPDATE_FARMS:
                # добавляем цели в фарм лист
                self._update_farm_lists()

            self._sanitizing()

            sleep_time = self.RUN_TIMEOUT + self.RUN_TIMEOUT * random.random()
            logging.info('sleep random time %f %d', sleep_time, self.loop_number)
            time.sleep(sleep_time)

    def _sanitizing(self):
        for close in self.driver.find_elements_by_id('dialogCancelButton'):
            close.click()
        self.driver.get(self.MAIN_PAGE)
        for close in self.driver.find_elements_by_id('dialogCancelButton'):
            close.click()

    def _quest_complete(self):
        logging.info('complete quest call')
        self.driver.get(self.MAIN_PAGE)

        # open quest dialog
        try:
            quest_master = self.driver.find_element_by_id('questmasterButton')
            quest_master.click()
        except NoSuchElementException:
            logging.info('all quest completed')
            return

        # ранние квесты
        def _process_early_quest():
            try:
                complete_button = self.driver.find_element_by_xpath('//button[@questbuttonnext="1"]')
                complete_button.click()
                logging.info('complete early quest')
                send_desktop_notify('complete early quest')
            except NoSuchElementException:
                return

        # поздние квесты
        def _process_late_quest(quest_list):
            for q in quest_list.find_elements_by_xpath('.//li[@class="questName"]'):
                try:
                    complete_flag = q.find_element_by_xpath('.//img[@class="reward"]')
                except NoSuchElementException:
                    continue

                link = q.find_element_by_tag_name('a')
                logging.debug('found quest for complete %s', str(link.text))
                link.click()

                complete_button = self.driver.find_element_by_xpath('//button[@questbuttongainreward="1"]')
                complete_button.click()
                logging.info('complete late quest')
                send_desktop_notify('complete late quest')
                break

        try:
            quest_list = self.driver.find_element_by_id('questTodoListDialog')
        except NoSuchElementException:
            logging.info('early quest process')
            _process_early_quest()
        else:
            logging.info('late quest process')
            _process_late_quest(quest_list)

    def _login(self):
        logging.info('login call')
        try:
            self.driver.get(config.HOST)
            login_form = self.driver.find_element_by_name("login")
            login_form.find_element_by_name('name').send_keys(self.user)
            login_form.find_element_by_name('password').send_keys(self.passwd)
            login_form.submit()

            self.driver.find_element_by_id('village_map')
            self.is_logged = True
            logging.info('login success')
        except:
            logging.info('login not success')

        ajax_token = self._parse_ajax_token()
        logging.info('get ajax token %s', ajax_token)
        if not ajax_token:
            raise RuntimeError('ajax token not found')
        self.ajax_token = ajax_token
        
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
        self.resource_buildings = result_builds

    def _analyze_resource_production(self):
        self.driver.get(self.MAIN_PAGE)
        table = self.driver.find_element_by_id('production')
        result_production = {}
        for row in table.find_elements_by_tag_name('tr')[1:]:
            title = str(row.find_element_by_class_name('res').text)
            value = str(row.find_element_by_class_name('num').text).strip()
            value = int(re.findall(r'([-]?\d+)', value)[0])
            logging.debug('production %s %d', title, value)
            type = None
            if config.RESOURCE_CLAY_NAME in title:
                type = config.RESOURCE_CLAY
            elif config.RESOURCE_FOOD_NAME in title:
                type = config.RESOURCE_FOOD
            elif config.RESOURCE_WOOD_NAME in title:
                type = config.RESOURCE_WOOD
            elif config.RESOURCE_IRON_NAME in title:
                type = config.RESOURCE_IRON
            result_production[type] = value
        logging.info('resource production %s', result_production)
        assert len(result_production) == 4
        self.resource_production = result_production

    def _analyze_resource_stock(self):
        self.driver.get(self.MAIN_PAGE)
        stock_list = self.driver.find_element_by_id('stockBar')

        def _get_resource_type(title):
            if config.RESOURCE_CLAY_NAME in title:
                return config.RESOURCE_CLAY
            elif config.RESOURCE_FOOD_NAME in title:
                return config.RESOURCE_FOOD
            elif config.RESOURCE_WOOD_NAME in title:
                return config.RESOURCE_WOOD
            elif config.RESOURCE_IRON_NAME in title:
                return config.RESOURCE_IRON
            return config.RESOURCE_FOOD_FREE

        result_stock = {}
        for row in stock_list.find_elements_by_xpath('.//li[contains(@class,"stockBarButton")]'):
            title = str(row.find_element_by_tag_name('img').get_attribute('alt')).strip()
            value = str(row.find_element_by_xpath('.//span[contains(@class, "value")]').text).strip()
            value = int(re.findall(r'(\d+)', value)[0])
            logging.debug('stock %s %d', title, value)
            res_type = _get_resource_type(title)
            result_stock[res_type] = value
        logging.info('resource stock %s', result_stock)
        assert len(result_stock) == 5
        self.resource_stock = result_stock

    def _analyze_buildings_queue(self):
        self.driver.get(self.MAIN_PAGE)
        try:
            div = self.driver.find_element_by_class_name('buildingList')
            cnt = len(div.find_elements_by_class_name('buildDuration'))
        except NoSuchElementException:
            cnt = 0

        self.build_queue_slots = max(0, config.BUILD_QUEUE_SLOTS_LIMIT - cnt)
        logging.info('build queue free slots %d', self.build_queue_slots)

    def _analyze_hero(self):
        self.driver.get(self.HERO_PAGE)
        status_div = self.driver.find_element_by_id('attributes')
        value = status_div.find_element_by_class_name('health')\
            .find_element_by_xpath('.//td[contains(@class, "current")]').text.strip()
        value = int(re.findall(r'(\d+)', str(value))[0])
        self.hero_hp = max(100, value)
        logging.info('hero HP percent %d', self.hero_hp)

    def _send_hero_to_adventures(self):
        logging.info('send hero to adventure call')
        if not self.hero_hp > config.HERO_HP_THRESHOLD_FOR_ADVENTURE:
            logging.info('hero hp is smaller than threshold %s', self.hero_hp)
            return

        self.driver.get(self.HERO_ADVENTURE_PAGE)
        adventure_list = self.driver.find_element_by_id('adventureListForm')
        links = adventure_list.find_elements_by_xpath('.//a[@class="gotoAdventure arrow"]')
        logging.info('find %d available adventures', len(links))

        if links:
            links[0].click()

            try:
                adventure_send_button = self.driver.find_element_by_xpath('//form[@class="adventureSendButton"]'
                                                                          '//button[contains(@class, "green")]')
                time.sleep(5)
                adventure_send_button.click()
                logging.info('send to adventure success')
                send_desktop_notify('send to adventure')
            except NoSuchElementException:
                logging.info('send to adventure not available')

    def _get_resource_buildings(self):
        self.driver.get(self.MAIN_PAGE)
        map_content = self.driver.find_element_by_id('rx')
        builds = map_content.find_elements_by_tag_name('area')
        result_builds = []
        for b in builds:
            b_desc = str(b.get_attribute('alt'))
            logging.debug('analyze resource build %s', b_desc)
            if not config.RESOURCE_BUILD_PATTERN_LEVEL in b_desc:
                continue
            b_href = str(b.get_attribute('href'))
            b_id = re.findall(r'id=(\d+)', b_href)[0]
            b_level = re.findall(r'%s (\d+)' % config.RESOURCE_BUILD_PATTERN_LEVEL, str(b_desc))[0]
            b_type = None
            if config.RESOURCE_WOOD_MINE in b_desc:
                b_type = config.RESOURCE_WOOD
            elif config.RESOURCE_FOOD_MINE in b_desc:
                b_type = config.RESOURCE_FOOD
            elif config.RESOURCE_IRON_MINE in b_desc:
                b_type = config.RESOURCE_IRON
            elif config.RESOURCE_CLAY_MINE in b_desc:
                b_type = config.RESOURCE_CLAY
            result_builds.append({
                'id': int(b_id),
                'desc': b_desc,
                'type': b_type,
                'level': int(b_level),
                'href': b_href
            })
        return result_builds

    def _goto_farmlist(self):
        rally_point_href = self._find_rally_point()
        logging.debug('found rally point href %s', rally_point_href)
        if not rally_point_href:
            logging.warning('not found rally point')
            return False
        self.driver.get(rally_point_href)
        farm_list_tab = self.driver.find_element_by_xpath(
            '//a[@class="tabItem" and contains(text(), "%s")]' % config.FARM_LIST_TAB_PATTERN)
        farm_list_tab.click()
        time.sleep(5)
        return True

    def __search_farmlist_by_id(self, id):
        return self.driver.find_element_by_xpath('//div[@id="%s"]' % id)

    def __search_farmlist_id_by_title(self, title_pattern):
        farm_lists = self.driver.find_elements_by_xpath('//div[@id="raidList"]/div[contains(@class, "listEntry")]')
        for list_element in farm_lists:
            title = list_element.find_element_by_class_name('listTitleText').text
            logging.debug('search farm list %s', title)
            if title_pattern in title:
                return list_element.get_attribute('id')
        return None

    def _send_army_to_farm(self):
        if not config.AUTO_FARM_LISTS:
            logging.info('not found farm list for automate')
            return

        res = self._goto_farmlist()
        if not res:
            return

        farm_list_ids = []
        for title_pattern in config.AUTO_FARM_LISTS:
            logging.info('process farm list %s', title_pattern)
            id = self.__search_farmlist_id_by_title(title_pattern)
            if id:
                farm_list_ids.append(id)

        logging.info('fetch farm list ids %s', farm_list_ids)
        random.shuffle(farm_list_ids)
        logging.info('fetch farm list ids %s rand', farm_list_ids)
        for id in farm_list_ids:
            logging.info('process farm list id %s', id)

            logging.info('sort list')
            sort_column = self.__search_farmlist_by_id(id).find_element_by_xpath('.//td[contains(@class, "lastRaid") and contains(@class, "sortable")]')
            sort_column.click()
            time.sleep(5)

            logging.info('check all')
            self.__search_farmlist_by_id(id).find_element_by_xpath('.//div[@class="markAll"]/input').click()

            logging.info('uncheck slots')
            slots = self.__search_farmlist_by_id(id).find_elements_by_class_name('slotRow')
            for tr in slots:
                # ignore if currently attacked
                logging.info('uncheck slot')
                currently_attacked = False
                try:
                    currently_attacked_elem = tr.find_element_by_xpath('.//td[@class="village"]/img[contains(@class, "attack")]')
                    if config.FARM_LIST_ALREADY_ATTACK_PATTERN in currently_attacked_elem.get_attribute('alt'):
                        currently_attacked = True
                except NoSuchElementException:
                    pass

                # ignore if last raid was loses
                last_raid_result_losses = False
                try:
                    last_raid_result = tr.find_element_by_xpath('.//td[@class="lastRaid"]/img[contains(@class, "iReport")]')
                    if config.FARM_LIST_WON_PATTERN not in last_raid_result.get_attribute('alt'):
                        last_raid_result_losses = True
                except NoSuchElementException:
                    pass

                if last_raid_result_losses or currently_attacked:
                    checkbox_elem = tr.find_element_by_xpath('.//input[@type="checkbox"]')
                    checkbox_elem.click()

            logging.info('send farm')
            button = self.__search_farmlist_by_id(id).find_element_by_xpath('.//button[contains(@value, "%s")]' % config.FARM_LIST_SEND_BUTTON_PATTERN)
            button.click()

            # todo log message

    def _find_rally_point(self):
        self.driver.get(self.VILLAGE_PAGE)
        map_content = self.driver.find_element_by_id('village_map')
        builds = map_content.find_elements_by_tag_name('area')
        for b in builds:
            b_desc = str(b.get_attribute('alt'))
            logging.debug('analyze build %s', b_desc)
            if config.FARM_LIST_BUILDING_PATTERN in b_desc:
                return str(b.get_attribute('href'))
        return None

    def _update_farm_lists(self):
        if self.loop_number > 1:
            return

        logging.info('process autofill farm list')

        res = self._goto_farmlist()
        if not res:
            logging.warning('not found farm list link - pass')
            return

        for conf in config.AUTO_COLLECT_FARM_LISTS:
            logging.info('process farm collect config %s', conf)

            # click map
            self.driver.get(self.MAP_PAGE)
            time.sleep(3)

            # emulate ajax request for fetch response with selenium
            form_html = """
            <form id="randomFormId" method="POST" action="%s">
                <input type="text" name="cmd" value="mapPositionData"></input>
                <input type="text" name="data[x]" value="%d"></input>
                <input type="text" name="data[y]" value="%d"></input>
                <input type="text" name="data[zoomLevel]" value="3"></input>
                <input type="text" name="ajaxToken" value="%s"></input>
                <input type="submit"/>
            </form>
            """ % (self.MAP_DATA_PAGE, conf['center_x'], conf['center_y'], self.ajax_token)
            elem = self.driver.find_element_by_tag_name('body')
            script = "arguments[0].innerHTML += '%s';" % form_html.replace("\n", '')
            logging.debug(script)

            self.driver.execute_script(script, elem)
            my_form = self.driver.find_element_by_id('randomFormId')
            my_form.submit()
            time.sleep(5)

            players = self._extract_players_from_source(self.driver.find_element_by_tag_name('pre').text)
            logging.info('found %d players', len(players))

            players_filter = self._apply_players_filter(players, conf)
            logging.info('filtered to %d players', len(players_filter))

            if not players_filter:
                return

            self._goto_farmlist()
            id = self.__search_farmlist_id_by_title(conf['list_name'])
            if not id:
                self.__create_farm_list(conf['list_name'])
                id = self.__search_farmlist_id_by_title(conf['list_name'])

            logging.info('farm list id %s', id)
            if not id:
                raise RuntimeError('not found farm list')

            for p in players_filter:
                self.__add_to_farm_list(id, p, conf['troop_id'], conf['troop_count'])
                logging.info('add player to farm %s', p['name'])

    def _parse_ajax_token(self):
        source = self.driver.page_source
        token_line = [i for i in source.split("\n") if 'ajaxToken' in i][0].strip()
        logging.debug(token_line)
        return token_line[-34:-2]

    @staticmethod
    def _extract_players_from_source(source):
        map_dict = loads(source)
        players = [i for i in map_dict['response']['data']['tiles'] if 'u' in i]
        result = []
        for p in players:
            try:
                inh = int(re.findall(r'\{k\.einwohner\}\s*(\d+)<br\s+/>', p['t'])[0])
            except IndexError:
                # pass players oasis
                continue
            ally = re.findall(r'\{k\.allianz\}\s*(.+)<br\s+/>\{k\.volk\}', p['t'])[0].strip()
            race_num = int(re.findall(r'\{k\.volk\}\s*\{a\.v(\d{1})\}', p['t'])[0].strip())
            name = re.findall(r'\{k\.spieler\}\s*(.+)<br\s+/>\{k\.einwohner\}', p['t'])[0].strip()
            result.append({
                'x': int(p['x']),
                'y': int(p['y']),
                'id': int(p['u']),
                'ally': ally,
                'name': name,
                'race': race_num,
                'inh': inh,
            })
        return result

    @staticmethod
    def _apply_players_filter(players, conf):
        result = [p for p in players if p['name'] not in config.IGNORE_FARM_PLAYERS and
                            p['ally'] not in config.IGNORE_FARM_ALLY]
        logging.info('filtered by ignore config %d', len(result))

        if 'ignore_npc' in conf and conf['ignore_npc']:
            result = [p for p in result if p['race'] != 5]
        if 'only_npc' in conf and conf['only_npc']:
            result = [p for p in result if p['race'] == 5]
        logging.info('filtered by race %d', len(result))

        if 'inh' in conf:
            min = 0 if 'min' not in conf['inh'] else conf['inh']['min']
            max = 999999 if 'max' not in conf['inh'] else conf['inh']['max']
            result = [p for p in result if min <= p['inh'] <= max]
        logging.info('filtered by inh %d', len(result))

        return result

    def __create_farm_list(self, list_name):
        logging.info('create new farm list %s', list_name)
        village_name, list_name = list_name.split(' - ')

        self.driver.find_element_by_xpath('//div[@class="options"]/a[@class="arrow"]').click()
        time.sleep(5)

        create_elem = self.driver.find_element_by_id('raidListCreate')
        create_elem.find_element_by_xpath('.//input[@name="listName"]').send_keys(list_name)

        select = Select(create_elem.find_element_by_id('did'))
        select.select_by_visible_text(village_name)

        create_elem.find_element_by_xpath('.//button[@value="Create"]').click()
        time.sleep(5)
        self._goto_farmlist()

    def __add_to_farm_list(self, id, p, troop_id, troop_count):
        time.sleep(3)
        self.__search_farmlist_by_id(id).find_element_by_xpath('.//div[@class="addSlot"]/button[@value="Add"]').click()
        time.sleep(5)

        form = self.driver.find_element_by_id('raidListSlot')
        form.find_element_by_id('xCoordInput').clear()
        form.find_element_by_id('xCoordInput').send_keys(p['x'])
        form.find_element_by_id('yCoordInput').clear()
        form.find_element_by_id('yCoordInput').send_keys(p['y'])

        troop_input = form.find_element_by_xpath('.//input[@id="%s"]' % troop_id)
        troop_input.clear()
        troop_input.send_keys(str(troop_count))

        form.find_element_by_id('save').click()


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
    logging.info('run %s %s' % config.CREDS)

    m = Manager(*config.CREDS)
    try:
        m.run()

    except Exception as e:
        logging.error('exception %s', e)
        send_desktop_notify('ЙА УПАЛО =(')
        # todo save screenshot
        raise e

    finally:
        m.close()


