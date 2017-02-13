#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import time
import datetime
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
import config_utils


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


def extract_oases_enemy_strength_from_source(source):
    map_dict = loads(source)
    document = l.fromstring(map_dict['response']['data']['html'].strip())
    out = 0
    for tr in document.xpath('//table[@id="troop_info"]//td[@class="val"]/parent::tr'):
        count = int(tr.xpath('.//td[@class="val"]/text()')[0].strip())
        name = tr.xpath('.//td[@class="desc"]/text()')[0].strip()
        logging.info('oases analize %s %d', name, count)
        try:
            index = [i for i in config.NATURE_ENEMIES_STRENGTH if i in name][0]
            strength = count * config.NATURE_ENEMIES_STRENGTH[index]
            out += strength
        except IndexError:
            logging.warning('undefined nature troop %s', name)

    return out


def check_already_attacked_farm(source):
    return config.FARM_LIST_ALREADY_ATTACK_PATTERN in source


def check_green_losses_farm(source):
    return config.FARM_LIST_ATTACK_PATTERN1 in source


def check_recently_attacked_farm(source, current_timestamp):
    if not current_timestamp:
        return False

    res = re.findall(config.REPORTS_TIME_PATTERN, source, re.MULTILINE)
    if not res:
        return False

    hour, minute = res[0]
    server_time = datetime.datetime.utcfromtimestamp(current_timestamp)
    attack_time = server_time.replace(hour=int(hour), minute=int(minute))
    delta = server_time - attack_time
    return int(delta.total_seconds()) <= config.SEND_FARMS_MIN_INTERVAL


def check_orange_losses_farm(source):
    return config.FARM_LIST_ATTACK_PATTERN2 in source


def check_full_carry_farm(source):
    return config.FARM_LIST_CARRY_FULL_PATTERN in source


def check_red_losses_farm(source):
    return config.FARM_LIST_ATTACK_PATTERN3 in source


class Manager(object):

    MAIN_PAGE = config.HOST + '/dorf1.php'
    VILLAGE_PAGE = config.HOST + '/dorf2.php'
    TROOPS_OVERVIEW_PAGE = config.HOST + '/dorf3.php?s=5'
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
    current_timestamp = 0
    ajax_token = ''

    def __init__(self, user, passwd):
        os.environ["webdriver.chrome.driver"] = config.CHROME_DRIVER_PATH
        self.driver = webdriver.Chrome(executable_path=config.CHROME_DRIVER_PATH)
        self.driver.set_page_load_timeout(config.REQUEST_TIMEOUT)
        self.driver.implicitly_wait(config.FIND_TIMEOUT)

        self._login(user, passwd)
        if not self.is_logged:
            raise RuntimeError('login error')

    def close(self):
        if self.driver:
            self.driver.quit()

    def run(self):
        while True:
            logging.info("\n")
            self.loop_number += 1
            self._sanitizing()

            # анализируем деревню
            self._analyze()

            # строим войска
            if config.ENABLE_BUILD_TROOPS:
                logging.info("\n")
                try:
                    self._build_troops()
                except Exception as e:
                    logging.error('troop building process exception %s', e)

            # remove uninteresting reports
            if config.ENABLE_REMOVE_FARM_REPORTS:
                logging.info("\n")
                try:
                    self._remove_uninteresting_reports()
                except Exception as e:
                    logging.error('reports remove process exception %s', e)

            # проверяем вражеские налёты
            if config.ENABLE_ATTACK_NOTIFY:
                logging.info("\n")
                try:
                    self._notify_about_attack()
                except Exception as e:
                    logging.error('notify about attack exception %s', e)

            # отправляем героя в приключения
            if config.ENABLE_ADVENTURES:
                logging.info("\n")
                try:
                    self._send_hero_to_adventures()
                except Exception as e:
                    logging.error('adventures process exception %s', e)

            # отправляем героя на прокачку в джунгли
            if config.ENABLE_HERO_TERROR:
                logging.info("\n")
                try:
                    self._send_hero_to_nature()
                except Exception as e:
                    logging.error('hero terror process exception %s', e)

            # забираем награды за квесты
            if config.ENABLE_QUEST_COMPLETE:
                logging.info("\n")
                try:
                    self._quest_complete()
                except Exception as e:
                    logging.error('quests process exception %s', e)

            # торгуем (пока только покупаем)
            if config.ENABLE_TRADE:
                logging.info("\n")
                try:
                    self._trading()
                except Exception as e:
                    logging.error('trade process exception %s', e)

            # шлём пылесосы по фарм листам
            if config.ENABLE_SEND_FARMS and (not float(self.loop_number) % config.SEND_FARMS_FACTOR or self.loop_number == 1):
                logging.info("\n")
                try:
                    self._send_army_to_farm()
                except Exception as e:
                    logging.error('farm send process exception %s', e)

            # обновляем фарм листы
            if config.ENABLE_CLEAR_FARMS and config.ENABLE_UPDATE_FARMS \
                    and not float(self.loop_number) % config.CLEAR_FARM_LIST_FACTOR:
                logging.info("\n")
                try:
                    self._clear_farm_lists()
                except Exception as e:
                    logging.error('farm clear process exception %s', e)

            # обновляем фарм листы
            if config.ENABLE_UPDATE_FARMS and not float(self.loop_number) % config.UPDATE_FARM_LIST_FACTOR:
                logging.info("\n")
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

    def _login(self, user, passw):
        logging.info('login call')
        try:
            self.driver.get(config.HOST)
            login_form = self.driver.find_element_by_name("login")
            login_form.find_element_by_name('name').send_keys(user)
            login_form.find_element_by_name('password').send_keys(passw)
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
        self._analyze_hero()
        self._analyze_time()

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

    def _analyze_time(self):
        try:
            self.current_timestamp = int(self.driver.find_element_by_id('servertime')
                                         .find_element_by_xpath('.//span[@class="timer"]').get_attribute('value'))
            logging.info('current time is %d', self.current_timestamp)
        except:
            logging.warning('time analyze error')
            self.current_timestamp = 0

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
                                                                '//img[@class="att1" or @class="att3"]'
                                                                '/ancestor::tr//span[@class="timer"]')
                logging.info('find attack timer %s', attack_timer_elem.text)
                attack_timing.append(int(attack_timer_elem.get_attribute('value')))
            except NoSuchElementException:
                logging.info('not found enemy attacks')
                continue

        logging.info('found %d attack timings', len(attack_timing))

        if attack_timing:
            send_desktop_notify('found %d attacks (%s)' % (len(attack_timing), min(attack_timing)))
            if min(attack_timing) <= config.LOOP_TIMEOUT * 4.:
                config_utils.send_attack_notify('t-manager: found %d attacks (min time %d)' %
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

        # select oasis
        random.shuffle(oases)
        selected_coords = None
        for i in oases:
            logging.info('oases %s check', i)
            tile_info_source = self.__get_tile_info(*i)
            strength = extract_oases_enemy_strength_from_source(tile_info_source)
            logging.info('enemy strength %d', strength)
            if config.HERO_TERROR_MIN_ENEMIES_STRENGTH <= strength <= config.HERO_TERROR_MAX_ENEMIES_STRENGTH:
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
        if config.HERO_TERROR_ESCORT_COUNT:
            logging.info('add escort for hero %s %s',
                         config.HERO_TERROR_ESCORT_COUNT,
                         config.HERO_TERROR_ESCORT_UNIT)
            form_elem.find_element_by_xpath('.//input[@name="%s"]' % config.HERO_TERROR_ESCORT_UNIT)\
                .send_keys(config.HERO_TERROR_ESCORT_COUNT)

        form_elem.find_element_by_xpath('.//div[@class="option"]//input[@value="4"]').click()
        form_elem.submit()
        custom_wait()

        logging.info('confirm send')
        self.driver.find_element_by_class_name('rallyPointConfirm').click()
        custom_wait()

    def _build_troops(self):
        logging.info('troops build call')

        for village, configs in config.AUTO_TROOP_BUILD.items():
            for conf in configs:
                logging.info('process %s %s', village, conf)

                # check current count total
                current_unit_total = self.__find_current_unit_count(conf['troop_id'], village)
                logging.info('current unit count %d', current_unit_total)
                if current_unit_total >= conf['troop_max']:
                    logging.info('total already max')
                    continue

                need_train = conf['troop_max'] - current_unit_total

                self.__select_village(village)
                logging.info('select village %s', village)

                # found building for troop type
                unit_input_elem = self.__find_troop_train_building(conf['troop_id'])
                if not unit_input_elem:
                    logging.warning('unit build not found')
                    continue

                # check available for build
                elem = unit_input_elem.find_element_by_xpath('./following-sibling::a')
                available_unit_count = int(elem.text)
                logging.info('found available unit count %d', available_unit_count)
                if available_unit_count <= 0:
                    logging.info('not found available units')
                    continue

                # check current queue
                unit_name = str(unit_input_elem.find_element_by_xpath('./preceding-sibling::div[contains(@class, "tit")]/a[2]').text)
                logging.info('unit name is %s', unit_name)
                queue_elems = self.driver.find_elements_by_xpath('//table[@class="under_progress"]//td[@class="desc" and contains(string(), "%s")]' % unit_name)
                logging.debug('found %d current queue tasks', len(queue_elems))
                already_queue_count = 0
                for e in queue_elems:
                    text = str(e.text).strip()
                    cnt = int(re.findall(r'([0-9]+)', text, re.MULTILINE)[0])
                    logging.debug("counting '%s' %d", text, cnt)
                    already_queue_count += cnt
                logging.info('found already queue task %d', already_queue_count)
                if already_queue_count >= conf['troop_queue_max']:
                    logging.info('queue is full')
                    continue

                # build with check village
                task_value = min(
                    available_unit_count,
                    need_train - already_queue_count,
                    conf['troop_queue_max'] - already_queue_count)
                if task_value <= 0:
                    logging.info('not need train more')
                    continue

                logging.info('send new troop build task %d', task_value)
                unit_input_elem.clear()
                unit_input_elem.send_keys(str(task_value))
                self.driver.find_element_by_xpath('//button[@type="submit" and contains(@class, "startTraining")]').click()
                send_desktop_notify('troop train %s %s %s' % (village, conf['troop_id'], task_value))

    def _send_army_to_farm(self):
        logging.info('send army to farm call')
        patterns = config.AUTO_FARM_LISTS
        if not patterns:
            logging.info('not found farm list for automate')
            return

        random.shuffle(patterns)
        for title in patterns:
            logging.info('process farm list %s', title)

            self.__goto_farmlist()
            farm_list_id = self.__search_farmlist_id_by_title(title)
            if not farm_list_id:
                logging.warning('not found list')
                continue

            # todo check available troops for green slots
            # todo check available troops for orange slots

            slots = self.__get_all_slots_by_farm_list(farm_list_id)
            enemies = []
            for tr in slots:
                raw_content = tr.get_attribute('innerHTML')
                if not check_already_attacked_farm(raw_content):
                    red_for_me = check_red_losses_farm(raw_content)
                    id = tr.find_element_by_xpath('.//input[@type="checkbox"]').get_attribute('id')
                    link = tr.find_element_by_xpath('.//td[@class="village"]/a').get_attribute('href')
                    enemies.append({'id': id, 'link': link, 'is_red': red_for_me})
            logging.info('found %d slots - filtered to %d', len(slots), len(enemies))
            if not enemies:
                continue

            green_full, green_other, orange_full, orange_other = self.__filter_farms_by_last_report(enemies)
            logging.info('sorting to %d green full, %d green other, %d orange full, %d orange other',
                         len(green_full), len(green_other), len(orange_full), len(orange_other))

            if green_full:
                logging.info('try send %d green full', len(green_full))
                self.__send_farm(farm_list_id, green_full, sort_by_distance=True)

            if green_other:
                logging.info('try send %d green other', len(green_other))
                self.__send_farm(farm_list_id, green_other, sort_by_lastraid=True)

            if config.ENABLE_SEND_CANNON_RUBBER_FARMS:
                if orange_full:
                    logging.info('try send %d orange full', len(orange_full))
                    for slot in enemies:
                        if slot['id'] not in orange_full:
                            continue
                        res = self.__send_orange_farm(slot['link'])
                        if res is False:
                            break
                if orange_other:
                    logging.info('try send %d orange other', len(orange_other))
                    for slot in enemies:
                        if slot['id'] not in orange_other:
                            continue
                        res = self.__send_orange_farm(slot['link'])
                        if res is False:
                            break

    def _clear_farm_lists(self):
        logging.info('process clear farm list')
        res = self.__goto_farmlist()
        if not res:
            logging.warning('not found farm list link - pass')
            return

        names = set([l['list_name'] for l in config.AUTO_UPDATE_FARM_LISTS])
        logging.info('select %d lists for remove', len(names))
        for name in names:
            logging.info('process clear farm list %s', name)
            while True:
                id = self.__search_farmlist_id_by_title(name)
                if not id:
                    logging.info('farm list already cleared')
                    break
                self.__remove_farm_list(id)
                send_desktop_notify('remove farm list %s' % name)

    def _update_farm_lists(self):
        logging.info('process autofill farm list')
        res = self.__goto_farmlist()
        if not res:
            logging.warning('not found farm list link - pass')
            return

        exist_villages = self.__extract_exist_villages_from_farmlist()
        logging.info('found %d already exist villages', len(exist_villages))

        lists = config.AUTO_UPDATE_FARM_LISTS
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
                    bid_link = next_bid_elem.find_element_by_xpath('.//td[@class="bid"]/a[contains(text(), "bid")]')
                except NoSuchElementException:
                    logging.warning('not found bid link')
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

    def __extract_summary_casualties(self):
        total = 0
        casualties = 0
        try:
            table = self.driver.find_element_by_id('attacker')
        except NoSuchElementException:
            logging.warning('not found attacker info on report view')
        else:
            expression = './/th[contains(text(), "%s")]/parent::tr/td[contains(@class, "unit") and text() != "0"]'
            troops = table.find_elements_by_xpath(expression % config.REPORTS_TROOPS_PATTERN)
            casualties = table.find_elements_by_xpath(expression % config.REPORTS_CASUALTIES_PATTERN)
            prisoners = table.find_elements_by_xpath(expression % config.REPORTS_PRISONERS_PATTERN)
            logging.info('found %d casualties and %d prisoners and %d troops', len(casualties), len(prisoners), len(troops))
            total = sum([int(i.text) for i in troops])
            casualties = sum([int(i.text) for i in casualties + prisoners])
            logging.info('summary %d/%d', total, casualties)

        return total, casualties

    def __filter_farms_by_last_report(self, farms):
        green_full, green_other, orange_full, orange_other = [], [], [], []
        for i, v in enumerate(farms):
            id = v['id']
            logging.info('check last report %s %s', i, id)
            self.driver.get(v['link'])
            last_attack_report = None
            try:
                last_attack_report = self.driver.find_element_by_xpath('//table[@id="troop_info"]'
                                                                       '//td/img[contains(@class, "iReport")]'
                                                                       '[contains(@alt, "%s") or contains(@alt, "%s") or contains(@alt, "%s")]'
                                                                       '/parent::td'
                                                                       % (config.FARM_LIST_ATTACK_PATTERN1,
                                                                          config.FARM_LIST_ATTACK_PATTERN2,
                                                                          config.FARM_LIST_ATTACK_PATTERN3))
            except NoSuchElementException:
                logging.info('not found last attack report')

            if not last_attack_report:
                if not v['is_red']:
                    logging.info('mark as green other by not found last report')
                    green_other.append(id)
                continue

            source = last_attack_report.get_attribute('innerHTML')
            is_full_carry = check_full_carry_farm(source)
            is_green = check_green_losses_farm(source)
            is_orange = check_orange_losses_farm(source)
            is_today = config.REPORTS_TODAY_PATTERN in source
            is_recently_attacked = check_recently_attacked_farm(source, self.current_timestamp)

            if is_green and is_full_carry:
                logging.info('mark as green full')
                green_full.append(id)
                continue

            if is_orange and is_full_carry:
                logging.info('mark as orange full')
                orange_full.append(id)
                continue

            if is_green and not is_recently_attacked:
                logging.info('mark as green other by not recently attacked')
                green_other.append(id)
                continue

            if is_orange and not is_today:
                logging.info('mark as orange other by not today')
                orange_other.append(id)
                continue

            logging.info('skip farm slot')
            # if is_orange :
            #     try:
            #         link = last_attack_report.find_element_by_tag_name('a').get_attribute('href')
            #         logging.debug('report link %s', link)
            #         self.driver.get(link)
            #     except NoSuchElementException:
            #         logging.warning('not found report link')
            #         continue
            #     total, casualties = self.__extract_summary_casualties()

        return green_full, green_other, orange_full, orange_other

    def __find_troop_train_building(self, troop_id):

        def _search_input():
            return self.driver.find_element_by_xpath('//div[contains(@class, "trainUnits")]//input[@name="%s"]' % troop_id)

        try:
            self.driver.find_element_by_xpath(
                '//div[@id="sidebarBoxActiveVillage"]//button[contains(@class, "barracksWhite")]').click()
            unit_input_elem = _search_input()
            logging.info('unit found in barracks')
            return unit_input_elem
        except NoSuchElementException:
            pass

        try:
            self.driver.find_element_by_xpath(
                '//div[@id="sidebarBoxActiveVillage"]//button[contains(@class, "stableWhite")]').click()
            unit_input_elem = _search_input()
            logging.info('unit found in stable')
            return unit_input_elem
        except NoSuchElementException:
            pass

        try:
            self.driver.find_element_by_xpath(
                '//div[@id="sidebarBoxActiveVillage"]//button[contains(@class, "workshopWhite")]').click()
            unit_input_elem = _search_input()
            logging.info('unit found in workshop')
            return unit_input_elem
        except NoSuchElementException:
            pass

        return None

    def __find_current_unit_count(self, unit_id, village):
        self.driver.get(self.TROOPS_OVERVIEW_PAGE)
        return int(self.driver.find_element_by_xpath('//table[@id="troops"]'
                                                     '//th[contains(@class, "vil")]'
                                                     '/a[text()="%s"]'
                                                     '/ancestor::tr//td[%s]' %
                                                     (village, unit_id[1:])).text)

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

    def __get_all_slots_by_farm_list(self, id):
        return self.__search_farmlist_by_id(id).find_elements_by_class_name('slotRow')

    def __search_farmlist_by_id(self, id):
        return self.driver.find_element_by_xpath('//div[@id="%s"]' % id)

    def __search_farmlist_id_by_title(self, title_pattern):
        farm_lists = self.driver.find_elements_by_xpath('//div[@id="raidList"]/div[contains(@class, "listEntry")]')
        for list_element in farm_lists:
            title = str(list_element.find_element_by_class_name('listTitleText').text).strip()
            logging.info('search farm list %s', title)
            if title_pattern == title:
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

        create_elem.find_element_by_xpath(
            './/button[@value="%s"]' % config.FARM_LIST_CREATE_BUTTON_PATTERN).click()
        custom_wait()
        self.__goto_farmlist()

    def __remove_farm_list(self, list_id):
        logging.info('remove farm list %s', list_id)
        self.__search_farmlist_by_id(list_id).find_element_by_xpath('.//button[@id="deleteRaidList"]').click()
        custom_wait()
        self.driver.find_element_by_xpath('//button[@type="submit" and contains(@class, "dialogButtonOk")]').click()
        custom_wait()

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

    def __send_orange_farm(self, link):
        logging.info('send to %s', link)
        self.driver.get(link)
        try:
            self.driver.find_element_by_partial_link_text(config.SEND_TROOPS_BUTTON_PATTERN).click()
        except NoSuchElementException:
            logging.warning('not found send troop button')
            return

        logging.info('select village %s', config.SEND_FARMS_CANNON_FODDER_VILLAGE)
        self.__select_village(config.SEND_FARMS_CANNON_FODDER_VILLAGE)

        # check count troops
        try:
            unit_input_elem = self.driver.find_element_by_xpath(
                '//table[@id="troops"]//input[@name="%s"]' % config.SEND_FARMS_CANNON_FODDER_UNIT)
            elem = unit_input_elem.find_element_by_xpath('./following-sibling::a')
            available_unit_count = int(elem.text)
            logging.info('found available troops count %d', available_unit_count)
            if available_unit_count < config.SEND_FARMS_CANNON_FODDER_COUNT:
                logging.warning('not enough troops')
                return False
        except NoSuchElementException:
            logging.warning('not found available troops elem')
            return False

        # send army
        unit_input_elem.clear()
        unit_input_elem.send_keys(str(config.SEND_FARMS_CANNON_FODDER_COUNT))
        self.driver.find_element_by_xpath('//input[@type="radio" and @value="4"]').click()
        self.driver.find_element_by_xpath('//button[@type="submit" and @id="btn_ok"]').click()
        self.driver.find_element_by_class_name('rallyPointConfirm').click()
        logging.info('send cannon rubber farm band')
        send_desktop_notify('send cannon rubber farm band')
        return True

    def __send_farm(self, id, slot_ids, sort_by_distance=False, sort_by_lastraid=False):
        self.__goto_farmlist()
        if sort_by_distance:
            logging.info('sort list by distance')
            sort_column = self.__search_farmlist_by_id(id).find_element_by_xpath(
                './/td[contains(@class, "lastRaid") and contains(@class, "sortable")]')
            sort_column.click()
            custom_wait()
            sort_column = self.__search_farmlist_by_id(id).find_element_by_xpath(
                './/td[contains(@class, "distance") and contains(@class, "sortable")]')
            sort_column.click()
            custom_wait()

        if sort_by_lastraid:
            logging.info('sort list by last raid')
            sort_column = self.__search_farmlist_by_id(id).find_element_by_xpath(
                './/td[contains(@class, "distance") and contains(@class, "sortable")]')
            sort_column.click()
            custom_wait()
            sort_column = self.__search_farmlist_by_id(id).find_element_by_xpath(
                './/td[contains(@class, "lastRaid") and contains(@class, "sortable")]')
            sort_column.click()
            custom_wait()

        selected = False
        for tr in self.__get_all_slots_by_farm_list(id):
            raw_content = tr.get_attribute('innerHTML')

            # ignore if currently attacked
            if check_already_attacked_farm(raw_content):
                continue

            checkbox_elem = tr.find_element_by_xpath('.//input[@type="checkbox"]')
            if checkbox_elem.get_attribute('id') in slot_ids:
                checkbox_elem.click()
                selected = True

        if not selected:
            logging.info('not selected raids')
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

    def __select_village(self, name):
        village_link = self.driver.find_element_by_xpath('//div[@id="sidebarBoxVillagelist"]//li//a'
                                                  '/div[@class="name" and contains(text(), "%s")]'
                                                  '/parent::a' % name)
        village_link.click()
        custom_wait()


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
