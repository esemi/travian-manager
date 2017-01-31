#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import time
from json import loads
import os
import random
import re
from shlex import quote

import lxml.html as l
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import Select

import config


def custom_wait():
    time.sleep(config.CUSTOM_WAIT_TIMEOUT)


def send_desktop_notify(message):
    os.system('notify-send "%s" "%s"' % ('travian-bot event', quote(message).replace('`', '\`')))


def unique_village_mask(name, x, y):
    return '_'.join([name.strip(), str(x), str(y)])


def apply_players_filter(players, conf, exist_villages):
    result = players
    result = [p for p in result if p['name'] not in config.IGNORE_FARM_PLAYERS and
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

    result = [p for p in result if unique_village_mask(p['v_name'], p['x'], p['y']) not in exist_villages]
    logging.info('filtered by already exist %d', len(result))

    return result


def extract_players_from_source(source):
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
        village_name = re.findall(r'\{k\.dt\}\s*(.*)', p['c'])[0].strip()
        result.append({
            'x': int(p['x']),
            'y': int(p['y']),
            'id': int(p['u']),
            'ally': ally,
            'name': name,
            'race': race_num,
            'inh': inh,
            'v_name': village_name
        })
    return result


def extract_free_oases_from_source(source):
    map_dict = loads(source)
    oases = [(int(i['x']), int(i['y'])) for i in map_dict['response']['data']['tiles']
             if 'd' in i and 't' in i and 'u' not in i and i['d'] == -1 and ('25%' in i['t'] or '50%' in i['t'])]
    return oases


def extract_oases_enemies_from_source(source):
    map_dict = loads(source)
    document = l.fromstring(map_dict['response']['data']['html'].strip())
    troop_rows = document.xpath('//table[@id="troop_info"]//td[@class="val"]/text()')
    return sum([int(i.strip()) for i in troop_rows])


class Manager(object):

    MAIN_PAGE = config.HOST + '/dorf1.php'
    VILLAGE_PAGE = config.HOST + '/dorf2.php'
    HERO_PAGE = config.HOST + '/hero.php'
    REPORTS_PAGE = config.HOST + '/berichte.php'
    HERO_ADVENTURE_PAGE = config.HOST + '/hero.php?t=3'
    AUCTION_PAGE = config.HOST + '/hero.php?t=4&action=buy'
    MAP_PAGE = config.HOST + '/karte.php'
    MAP_DATA_PAGE = config.HOST + '/ajax.php?cmd=mapPositionData'
    TILE_DATA_PAGE = config.HOST + '/ajax.php?cmd=viewTileDetails'
    FARM_LIST_PAGE = None
    SEND_ARMY_PAGE = None

    loop_number = 0
    is_logged = False
    hero_hp = 0
    ajax_token = ''

    def __init__(self, user, passwd):
        self.user = user
        self.passwd = passwd

        os.environ["webdriver.chrome.driver"] = config.CHROME_DRIVER_PATH
        self.driver = webdriver.Chrome(executable_path=config.CHROME_DRIVER_PATH)
        self.driver.set_page_load_timeout(config.REQUEST_TIMEOUT)
        self.driver.implicitly_wait(config.FIND_TIMEOUT)

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

            # remove uninteresting reports
            if config.ENABLE_REMOVE_FARM_REPORTS:
                try:
                    self._remove_uninteresting_reports()
                except Exception as e:
                    logging.error('reports remove process exception %s', e)

            # проверяем вражеские налёты
            if config.ENABLE_ATTACK_NOTIFY:
                try:
                    self._notify_about_attack()
                except Exception as e:
                    logging.error('notify about attack exception %s', e)

            # отправляем героя в приключения
            if config.ENABLE_ADVENTURES:
                try:
                    self._send_hero_to_adventures()
                except Exception as e:
                    logging.error('adventures process exception %s', e)

            # отправляем героя на прокачку в джунгли
            if config.ENABLE_HERO_TERROR:
                try:
                    self._send_hero_to_nature()
                except Exception as e:
                    logging.error('hero terror process exception %s', e)

            # забираем награды за квесты
            if config.ENABLE_QUEST_COMPLETE:
                try:
                    self._quest_complete()
                except Exception as e:
                    logging.error('quests process exception %s', e)

            # шлём пылесосы по фарм листам
            if config.ENABLE_SEND_FARMS:
                try:
                    self._send_army_to_farm()
                except Exception as e:
                    logging.error('farm send process exception %s', e)

            # торгуем (пока только покупаем)
            if config.ENABLE_TRADE:
                try:
                    self._trading()
                except Exception as e:
                    logging.error('trade process exception %s', e)

            # добавляем цели в фарм лист
            if config.ENABLE_UPDATE_FARMS:
                try:
                    self._update_farm_lists()
                except Exception as e:
                    logging.error('farm update process exception %s', e)

            if not config.DEBUG:
                self._sanitizing()

            sleep_time = config.LOOP_TIMEOUT + config.LOOP_TIMEOUT * random.random()
            logging.info('sleep random time %f %d', sleep_time, self.loop_number)
            time.sleep(sleep_time)

    def _sanitizing(self):
        self.__close_all_dialogs()
        try:
            self.driver.get(self.MAIN_PAGE)
        except:
            pass
        self.__close_all_dialogs()

    def _quest_complete(self):
        logging.info('complete quest call')
        self.driver.get(self.MAIN_PAGE)

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
            # open quest dialog
            quest_master = self.driver.find_element_by_id('questmasterButton')
            quest_master.click()
        except NoSuchElementException:
            logging.info('all quest completed')
        else:
            try:
                quest_list = self.driver.find_element_by_id('questTodoListDialog')
            except NoSuchElementException:
                logging.info('early quest process')
                _process_early_quest()
            else:
                logging.info('late quest process')
                _process_late_quest(quest_list)

        # complete daily
        try:
            quest_button = self.driver.find_element_by_class_name('questButtonOverviewAchievements')
            quest_button.click()
        except NoSuchElementException:
            logging.warning('not found daily quest button')
        else:
            try:
                reward_elem = self.driver.find_element_by_xpath('//div[@id="achievementRewardList"]'
                                                                '//div[contains(@class, "rewardReady")]')
                reward_elem.click()
                custom_wait()
                reward_button = self.driver.find_element_by_xpath('//button[contains(@class, "questButtonGainReward")]')
                reward_button.click()
                logging.info('daily quest complete')
            except NoSuchElementException:
                logging.info('not found daily reward')

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

        def _parse_ajax_token(source):
            token_line = [i for i in source.split("\n") if 'ajaxToken' in i][0].strip()
            logging.debug(token_line)
            return token_line[-34:-2]

        ajax_token = _parse_ajax_token(self.driver.page_source)
        logging.info('get ajax token %s', ajax_token)
        if not ajax_token:
            raise RuntimeError('ajax token not found')
        self.ajax_token = ajax_token
        
    def _analyze(self):
        logging.info('analyze call')

        # analyze hero
        self._analyze_hero()

    def _analyze_hero(self):
        try:
            self.driver.get(self.HERO_PAGE)
            status_div = self.driver.find_element_by_id('attributes')
            value = status_div.find_element_by_class_name('health')\
                .find_element_by_xpath('.//td[contains(@class, "current")]').text.strip()
            value = int(re.findall(r'(\d+)', str(value))[0])
            self.hero_hp = max(0, value)
            logging.info('hero HP percent %d', self.hero_hp)
        except:
            logging.warning('hero analyze error')
            self.hero_hp = 0

    def _notify_about_attack(self):
        logging.info('notify about attack call')
        self.driver.get(self.MAIN_PAGE)

        links = self.driver.find_elements_by_xpath('//div[@id="sidebarBoxVillagelist"]//li//a/div[@class="name"]'
                                                   '/parent::a')
        village_links = [link.get_attribute('href') for link in links]
        logging.info('found %d villages', len(village_links))

        attack_timing = []
        for link in village_links:
            logging.info('check attack %s village', link)
            self.driver.get(link)
            try:
                attack_timer_elem = self.driver.find_element_by_xpath('//div[@id="map_details"]'
                                                                '//div[contains(@class, "villageList")]'
                                                                '//img[@class="att1"]'
                                                                '/ancestor::tr//span[@class="timer"]')
                logging.info('find attack timer %s', attack_timer_elem.text)
                attack_timing.append(int(attack_timer_elem.get_attribute('value')))
            except NoSuchElementException:
                logging.info('not found enemy attacks')
                continue

        logging.info('found %d attack timings', len(attack_timing))
        logging.info(attack_timing)

        if attack_timing:
            send_desktop_notify('found %d attacks (%s)' % (len(attack_timing), min(attack_timing)))
            if min(attack_timing) <= config.LOOP_TIMEOUT * 4.:
                config.send_attack_notify('t-manager: found %d attacks (min time %d)' %
                                          (len(attack_timing), min(attack_timing)))

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
                custom_wait()
                adventure_send_button.click()
                logging.info('send to adventure success')
                send_desktop_notify('send to adventure')
            except NoSuchElementException:
                logging.info('send to adventure not available')

    def _send_hero_to_nature(self):
        logging.info('send hero to terror call %s', self.hero_hp)
        if self.hero_hp < config.HERO_HP_THRESHOLD_FOR_TERROR:
            logging.info('hero hp is smaller than threshold %s', self.hero_hp)
            return

        # check hero on home
        self.driver.get(self.HERO_PAGE)
        status_elem = self.driver.find_element_by_xpath('//div[contains(@class, "heroStatusMessage")]/span')
        if config.HERO_ON_HOME_PATTERN not in status_elem.text:
            logging.info('hero not on home - pass (%s)', status_elem.text)
            return

        village_name = status_elem.find_element_by_xpath('.//a').text.strip()
        logging.info('hero village %s', village_name)

        # select village
        village_link_elem = self.driver.find_element_by_xpath('//div[@id="sidebarBoxVillagelist"]//li//a'
                                                              '/div[@class="name" and contains(text(), "%s")]'
                                                              '/parent::a' % village_name)
        village_x = village_link_elem.find_element_by_class_name('coordinateX').get_attribute('innerHTML')
        village_x = int(re.findall(r'(-?\d+)', village_x)[0])

        village_y = village_link_elem.find_element_by_class_name('coordinateY').get_attribute('innerHTML')
        village_y = int(re.findall(r'(-?\d+)', village_y)[0])

        logging.info('hero village link %s %s %s', village_link_elem.get_property('href'), village_x, village_y)
        village_link_elem.click()
        custom_wait()

        # get all free oases
        source = self.__extract_map_data(village_x, village_y)
        oases = extract_free_oases_from_source(source)
        logging.info('found %d free oases', len(oases))

        # select first not empty oasis
        random.shuffle(oases)
        logging.info('minimum enemies is %s', config.HERO_TERROR_MIN_ENEMIES)
        selected_coords = None
        for i in oases:
            logging.info('oases %s check', i)
            tile_info_source = self.__get_tile_info(*i)
            count = extract_oases_enemies_from_source(tile_info_source)
            logging.info('enemies %d', count)
            if count >= config.HERO_TERROR_MIN_ENEMIES:
                selected_coords = i
                break

        if not selected_coords:
            logging.warning('not found full oasis?')
            return

        # send hero to selected oasis
        res = self.__goto_sendarmy_tab()
        if not res:
            logging.warning('not found send army tab')
            return

        logging.info('send hero to %s', selected_coords)
        form_elem = self.driver.find_element_by_xpath('//form[@name="snd"]')
        form_elem.find_element_by_xpath('.//input[@name="t11"]').send_keys(1)
        form_elem.find_element_by_id('xCoordInput').send_keys(selected_coords[0])
        form_elem.find_element_by_id('yCoordInput').send_keys(selected_coords[1])
        form_elem.find_element_by_xpath('.//div[@class="option"]//input[@value="4"]').click()
        form_elem.submit()
        custom_wait()

        logging.info('confirm send')
        self.driver.find_element_by_class_name('rallyPointConfirm').click()
        custom_wait()

    def _send_army_to_farm(self):
        logging.info('send army to farm call')
        if not config.AUTO_FARM_LISTS:
            logging.info('not found farm list for automate')
            return

        res = self.__goto_farmlist()
        if not res:
            return

        patterns = config.AUTO_FARM_LISTS
        random.shuffle(patterns)

        # send to carry full villages
        for title in patterns:
            logging.info('process farm list carry full %s', title)
            try:
                self.__send_farm_to_list(title, True)
            except Exception as e:
                logging.error('send farms exception %s', e)

        # send to all
        for title in patterns:
            logging.info('process farm list %s', title)
            try:
                self.__send_farm_to_list(title)
            except Exception as e:
                logging.error('send farms exception %s', e)

    def _update_farm_lists(self):
        if not float(self.loop_number) % config.UPDATE_FARM_LIST_FACTOR:
            return

        logging.info('process autofill farm list')
        res = self.__goto_farmlist()
        if not res:
            logging.warning('not found farm list link - pass')
            return

        exist_villages = self.__extract_exist_villages_from_farmlist()
        logging.info('found %d already exist villages', len(exist_villages))

        lists = config.AUTO_COLLECT_FARM_LISTS
        random.shuffle(lists)
        for conf in lists:
            logging.info('process farm collect config %s', conf)

            source = self.__extract_map_data(conf['center_x'], conf['center_y'])
            players = extract_players_from_source(source)
            logging.info('found %d players', len(players))

            players_filter = apply_players_filter(players, conf, exist_villages)
            logging.info('filtered to %d players', len(players_filter))

            if not players_filter:
                continue

            if not self.__goto_farmlist():
                continue

            for p in players_filter:
                id, title = self.__find_farmlist_for_add(conf['list_name'])
                if not id:
                    raise RuntimeError('not found farm list')
                self.__add_to_farm_list(id, p, conf['troop_id'], conf['troop_count'])
                mask = unique_village_mask(p['v_name'], p['x'], p['y'])
                logging.info('add player to farm %s %s', mask, title)
                exist_villages.add(mask)
                send_desktop_notify('add player to farm %s' % p['v_name'])

    def _trading(self):
        if not config.AUCTION_BIDS:
            return

        minimal_price = min(config.AUCTION_BIDS.values())
        logging.info('trading start: minimal bid is %d', minimal_price)
        self.driver.get(self.AUCTION_PAGE)

        i = 0
        while i < 100:
            i += 1
            try:
                logging.info('trade loop %d', i)
                silver_coins_str = self.driver.find_element_by_class_name('ajaxReplaceableSilverAmount').text
                coins_count = int(silver_coins_str)
                logging.info('free coins %d', coins_count)

                if coins_count < minimal_price:
                    logging.warning('coins too low')
                    return

                try:
                    next_bid_elem = self.driver.find_element_by_xpath('//div[@id="auction"]//tbody/tr[%d]' % i)
                except NoSuchElementException:
                    logging.info('not found next bid %d', i)
                    break

                item_price = int(next_bid_elem.find_element_by_class_name('silver').text)
                logging.info('item cost %s', item_price)

                if coins_count < item_price:
                    logging.info('skip by coins amount %d %d', item_price, coins_count)
                    continue

                item_name_str = next_bid_elem.find_element_by_class_name('name').text
                logging.info('item name string %s', item_name_str)

                item_count = int(re.findall(r'(\d+)‬×‬', item_name_str)[0])
                logging.info('item count %d', item_count)

                item_bid = None
                for pattern, bid_value in config.AUCTION_BIDS.items():
                    if pattern in item_name_str:
                        logging.info('select %s item %d', pattern, bid_value)
                        item_bid = bid_value
                        break

                if not item_bid:
                    logging.info('skip not interested item')
                    continue

                if item_price / item_count >= item_bid:
                    logging.info('skip by price')
                    continue

                try:
                    bid_link = next_bid_elem.find_element_by_xpath('.//td[@class="bid"]/a[contains(text(), "Bid")]')
                except NoSuchElementException:
                    logging.info('not found bid link')
                    continue
                bid_link.click()

                bid = item_bid * item_count
                logging.info('bid try %d', bid)
                custom_wait()

                self.driver.find_element_by_xpath('//input[@name="maxBid"]').send_keys(str(bid))
                self.driver.find_element_by_xpath('//div[@class="submitBid"]/button[@type="submit"]').click()
            except Exception as e:
                logging.error(e)
            else:
                logging.info('bid save')
                custom_wait()
                send_desktop_notify('trade: bid item %s by %d' % (item_name_str, bid))
                self.driver.get(self.AUCTION_PAGE)

    def _remove_uninteresting_reports(self):
        logging.info('remove reports call')
        self.driver.get(self.REPORTS_PAGE)
        reports_for_delete = self.driver.find_elements_by_xpath('//form[@id="reportsForm"]'
                                                                '//table[@id="overview"]'
                                                                '//td[contains(@class, "sub")]'
                                                                '//img[contains(@alt, "%s") and contains(@class, "iReport1")]'
                                                                '/ancestor::tr'
                                                                '/td[contains(@class, "sel")]'
                                                                '//input[@type="checkbox"]'
                                                                % config.REPORTS_ATTACK_PATTERN1)
        logging.info('found %d reports for delete', len(reports_for_delete))
        for checkbox in reports_for_delete:
            checkbox.click()

        if reports_for_delete:
            self.driver.find_element_by_id('del').click()
            custom_wait()

    def __goto_farmlist(self):
        if not self.FARM_LIST_PAGE:
            rally_point_href = self.__find_rally_point_build()
            logging.debug('found rally point href %s', rally_point_href)
            if not rally_point_href:
                logging.warning('not found rally point')
                return False

            self.driver.get(rally_point_href)
            farm_list_tab = self.driver.find_element_by_xpath(
                '//a[@class="tabItem" and contains(text(), "%s")]' % config.FARM_LIST_TAB_PATTERN)
            self.FARM_LIST_PAGE = farm_list_tab.get_attribute('href')

        self.driver.get(self.FARM_LIST_PAGE)
        custom_wait()
        return True

    def __goto_sendarmy_tab(self):
        if not self.SEND_ARMY_PAGE:
            rally_point_href = self.__find_rally_point_build()
            logging.debug('found rally point href %s', rally_point_href)
            if not rally_point_href:
                logging.warning('not found rally point')
                return False

            self.driver.get(rally_point_href)
            send_army_tab = self.driver.find_element_by_xpath(
                '//a[@class="tabItem" and contains(text(), "%s")]' % config.SEND_ARMY_TAB_PATTERN)
            self.SEND_ARMY_PAGE = send_army_tab.get_attribute('href')

        self.driver.get(self.SEND_ARMY_PAGE)
        custom_wait()
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

    def __find_farmlist_for_add(self, title_pattern):
        while True:
            id = self.__search_farmlist_id_by_title(title_pattern)
            if not id:
                self.__create_farm_list(title_pattern)
                send_desktop_notify('create new farm list %s' % title_pattern)
                id = self.__search_farmlist_id_by_title(title_pattern)
                return id, title_pattern

            free_slot_elem = self.__search_farmlist_by_id(id).find_element_by_xpath(
                './/div[@class="addSlot"]/span[@class="raidListSlotCount"]')

            counter = str(free_slot_elem.text)
            logging.info('counter %s', counter)
            usage = int(re.findall(r'(\d+)', counter)[0])
            total = int(re.findall(r'(\d+)', counter)[1])
            logging.info('counter %s %s', usage, total)
            if usage < total:
                return id, title_pattern

            logging.info('list is full - next loop')
            title_pattern += '_'

    def __extract_exist_villages_from_farmlist(self):
        res = []
        slots = self.driver.find_elements_by_xpath('//tr[@class="slotRow"]')
        for tr in slots:
            try:
                el = tr.find_element_by_class_name('village').find_element_by_tag_name('a')
                v_name = el.text
            except NoSuchElementException:
                continue

            try:
                x = int(re.findall(r'x=([-]?\d+)', el.get_attribute('href'))[0])
                y = int(re.findall(r'y=([-]?\d+)', el.get_attribute('href'))[0])
            except IndexError:
                logging.warning('invalid farmlist slot %s', v_name)
                continue

            res.append(unique_village_mask(v_name, x, y))
        return set(res)

    def __find_rally_point_build(self):
        self.driver.get(self.VILLAGE_PAGE)
        map_content = self.driver.find_element_by_id('village_map')
        builds = map_content.find_elements_by_tag_name('area')
        for b in builds:
            b_desc = str(b.get_attribute('alt'))
            logging.debug('analyze build %s', b_desc)
            if config.FARM_LIST_BUILDING_PATTERN in b_desc:
                return str(b.get_attribute('href'))
        return None

    def __extract_map_data(self, x: int, y: int):
        """emulate ajax request for fetch response with selenium"""
        self.driver.get(self.MAP_PAGE)
        custom_wait()

        form_html = """
            <form id="randomFormId" method="POST" action="%s">
                <input type="text" name="cmd" value="mapPositionData"></input>
                <input type="text" name="data[x]" value="%d"></input>
                <input type="text" name="data[y]" value="%d"></input>
                <input type="text" name="data[zoomLevel]" value="3"></input>
                <input type="text" name="ajaxToken" value="%s"></input>
                <input type="submit"/>
            </form>
            """ % (self.MAP_DATA_PAGE, x, y, self.ajax_token)
        elem = self.driver.find_element_by_tag_name('body')
        script = "arguments[0].innerHTML += '%s';" % form_html.replace("\n", '')
        logging.debug(script)

        self.driver.execute_script(script, elem)
        my_form = self.driver.find_element_by_id('randomFormId')
        my_form.submit()
        custom_wait()
        return self.driver.find_element_by_tag_name('pre').text

    def __get_tile_info(self, x: int, y: int):
        """emulate ajax request for fetch oasis info"""
        self.driver.get(self.MAP_PAGE)
        custom_wait()

        form_html = """
                <form id="randomFormId" method="POST" action="%s">
                    <input type="text" name="cmd" value="viewTileDetails"></input>
                    <input type="text" name="x" value="%d"></input>
                    <input type="text" name="y" value="%d"></input>
                    <input type="text" name="ajaxToken" value="%s"></input>
                    <input type="submit"/>
                </form>
                """ % (self.TILE_DATA_PAGE, x, y, self.ajax_token)
        elem = self.driver.find_element_by_tag_name('body')
        script = "arguments[0].innerHTML += '%s';" % form_html.replace("\n", '')
        logging.debug(script)

        self.driver.execute_script(script, elem)
        my_form = self.driver.find_element_by_id('randomFormId')
        my_form.submit()
        custom_wait()
        return self.driver.find_element_by_tag_name('pre').text

    def __create_farm_list(self, list_name):
        logging.info('create new farm list %s', list_name)
        village_name, list_name = list_name.split(' - ')

        self.driver.find_element_by_xpath('//div[@class="options"]/a[@class="arrow"]').click()
        custom_wait()

        create_elem = self.driver.find_element_by_id('raidListCreate')
        create_elem.find_element_by_xpath('.//input[@name="listName"]').send_keys(list_name)

        select = Select(create_elem.find_element_by_id('did'))
        select.select_by_visible_text(village_name)

        create_elem.find_element_by_xpath('.//button[@value="Create"]').click()
        custom_wait()
        self.__goto_farmlist()

    def __add_to_farm_list(self, id, p, troop_id, troop_count):
        custom_wait()
        self.__close_all_dialogs()
        self.__search_farmlist_by_id(id).find_element_by_xpath(
            './/div[@class="addSlot"]/button[@value="%s"]' % config.FARM_LIST_ADD_BUTTON_PATTERN).click()
        custom_wait()

        form = self.driver.find_element_by_id('raidListSlot')
        form.find_element_by_id('xCoordInput').clear()
        form.find_element_by_id('xCoordInput').send_keys(p['x'])
        form.find_element_by_id('yCoordInput').clear()
        form.find_element_by_id('yCoordInput').send_keys(p['y'])

        troop_input = form.find_element_by_xpath('.//input[@id="%s"]' % troop_id)
        troop_input.clear()
        troop_input.send_keys(str(troop_count))

        form.find_element_by_id('save').click()
        custom_wait()

    def __send_farm_to_list(self, title, carry_full_only=False):
        id = self.__search_farmlist_id_by_title(title)
        if not id:
            logging.warning('not found list')
            return

        if carry_full_only:
            logging.info('sort list by distance')
            sort_column = self.__search_farmlist_by_id(id).find_element_by_xpath(
                './/td[contains(@class, "lastRaid") and contains(@class, "sortable")]')
            sort_column.click()
            custom_wait()
            sort_column = self.__search_farmlist_by_id(id).find_element_by_xpath(
                './/td[contains(@class, "distance") and contains(@class, "sortable")]')
        else:
            logging.info('sort list by last raid')
            sort_column = self.__search_farmlist_by_id(id).find_element_by_xpath(
                './/td[contains(@class, "distance") and contains(@class, "sortable")]')
            sort_column.click()
            custom_wait()
            sort_column = self.__search_farmlist_by_id(id).find_element_by_xpath(
                './/td[contains(@class, "lastRaid") and contains(@class, "sortable")]')
        sort_column.click()
        custom_wait()

        logging.info('select villages')
        slots = self.__search_farmlist_by_id(id).find_elements_by_class_name('slotRow')
        selected = False
        for tr in slots:
            raw_content = tr.get_attribute('innerHTML')
            # ignore if currently attacked
            if config.FARM_LIST_ALREADY_ATTACK_PATTERN in raw_content:
                continue

            # ignore if last raid was loses
            if config.FARM_LIST_LOSSES_PATTERN1 in raw_content or config.FARM_LIST_LOSSES_PATTERN2 in raw_content:
                continue

            # ignore if last raid was not full cary
            if carry_full_only and config.FARM_LIST_CARRY_FULL_PATTERN not in raw_content:
                continue

            checkbox_elem = tr.find_element_by_xpath('.//input[@type="checkbox"]')
            checkbox_elem.click()
            selected = True

        if not selected:
            logging.info('not found raids')
            return

        logging.info('send farm')
        button = self.__search_farmlist_by_id(id).find_element_by_xpath(
            './/button[contains(@value, "%s")]' % config.FARM_LIST_SEND_BUTTON_PATTERN)
        button.click()
        custom_wait()
        try:
            result = self.__search_farmlist_by_id(id).find_element_by_xpath(
                './/p[contains(text(), "%s")]' % config.FARM_LIST_SEND_RESULT_PATTERN)
            logging.info('result message is %s', result.text)
        except NoSuchElementException:
            logging.warning('not found result message')

    def __close_all_dialogs(self):
        while True:
            elems = self.driver.find_elements_by_id('dialogCancelButton')
            if not elems:
                break
            for e in elems:
                try:
                    e.click()
                    custom_wait()
                except Exception as e:
                    pass

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
        if not config.DEBUG:
            m.close()


