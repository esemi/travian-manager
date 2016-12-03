#! /usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import logging

from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities


class Manager(object):

    TIMEOUT = 20
    HOST = 'http://ts1.travian.ru'
    is_logged = False
    VILLAGE_RESOURCE_BUILDINGS = {}

    def __init__(self, user, passwd):
        self.user = user
        self.passwd = passwd
        firefox_capabilities = DesiredCapabilities.FIREFOX
        firefox_capabilities['marionette'] = True
        firefox_capabilities['binary'] = '/usr/bin/firefox'
        self.driver = webdriver.Firefox(capabilities=firefox_capabilities, timeout=self.TIMEOUT)
        self.driver.implicitly_wait(self.TIMEOUT)

    def run(self):
        self.login()

        if not self.is_logged:
            logging.error('login error')
            return

        while True:
            # анализируем деревню
            self.analyze()
            # если есть свободные ресурсы и место в очереди
                # развиваем деревню (ресурсы и центр)

            # todo нотифаим если идёт атака
            # todo отправляем героя в приключения
            # todo прокачиваем героя
            # todo выполняем задания и забираем награды за них
            pass

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
        m.run()


