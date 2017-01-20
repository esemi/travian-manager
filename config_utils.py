# -*- coding: utf-8 -*-


def compute_autofarm_distances(x: int, y: int, offset: int, conf: dict):
    if not offset:
        return [dict(center_x=x, center_y=y, **conf)]
    out = [
        dict(center_x=x, center_y=y, **conf),
        dict(center_x=x+offset, center_y=y, **conf),
        dict(center_x=x+offset, center_y=y+offset, **conf),
        dict(center_x=x, center_y=y+offset, **conf),
        dict(center_x=x-offset, center_y=y+offset, **conf),
        dict(center_x=x-offset, center_y=y, **conf),
        dict(center_x=x-offset, center_y=y-offset, **conf),
        dict(center_x=x, center_y=y-offset, **conf),
        dict(center_x=x+offset, center_y=y-offset, **conf),
    ]
    return out


def send_attack_notify(message):
    import logging
    import requests
    from config import SMS_TO_PHONE, SMS_USER, SMS_PASS

    params = {
        'login': SMS_USER,
        'psw': SMS_PASS,
        'phones': SMS_TO_PHONE,
        'mes': message,
        'translit': 1,
        'cost': 0,
        'sender': '',
        'charset': 'utf-8',
    }
    logging.debug('send sms %s' % message)

    try:
        response = requests.get('http://smsc.ru/sys/send.php', params=params)
        response.raise_for_status()
    except Exception as e:
        logging.error('send sms exception %s' % e)
    else:
        logging.info('send sms response %s' % response.content)
        if not response.content.startswith(b'OK'):
            logging.error('send sms error response')
