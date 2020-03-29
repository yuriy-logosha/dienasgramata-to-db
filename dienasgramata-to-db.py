#!/usr/bin/env python3
import logging
import urllib.parse
import time

import pymongo

from utils import json_from_file, MyHTMLParser, _get, json_to_file

config_file_name = 'config.json'
config = {}

try:
    config = json_from_file(config_file_name, "Can't open ss-config file.")
except RuntimeError as e:
    print(e)
    exit()

formatter = logging.Formatter(config['logging.format'])
# Create handlers
c_handler = logging.StreamHandler()
f_handler = logging.FileHandler(config['logging.file'])

# Create formatters and add it to handlers
c_handler.setFormatter(formatter)
f_handler.setFormatter(formatter)

logging_level = config["logging.level"] if 'logging.level' in config else 20
print("Selecting logging level", logging_level)
print("Selecting logging format", config["logging.format"])
print("Selecting logging file \"%s\"" % config['logging.file'])

logging.basicConfig(format=config["logging.format"], handlers=[c_handler, f_handler])
logger = logging.getLogger(config["logging.name"])
logger.setLevel(logging_level)


def request_site():
    d = []
    try:
        for url in config["sites"]:
            parser_config = {'valid_tags': ['tr', 'td', 'a', 'b', 'span', 'div', 'h2']}
            d += MyHTMLParser(parser_config).feed_and_return(_get(url).content.decode()).data
    except RuntimeError as e:
        logger.debug(e)
    return d


def build_db_record(_date, _day, _subj, _hometask):
    try:
        a = {"kind": "exercise", "date": _date, "day": _day, "subject": _subj, "exercise": _hometask}
        return a
    except RuntimeError as e:
        logger.debug(e)
    return {}


subj = []


def is_title(d):
    if d[0] == 'span' and d[1] == [('class', 'title')]:
        return True
    return False


def is_date(d):
    if d[0] == 'h2' and d[1] == []:
        return True
    return False


def is_hometask(d):
    if d[0] == 'td' and d[1] == [('class', 'hometask')]:
        return True
    return False


def is_after_hometask(d, after_hometask):
    if after_hometask and ((d[0] == 'span' and 'title' in d[1][0]) or d[0] == 'a'):
        return True
    return False


def is_score(d):
    if d[0] == 'td' and d[1] == [('class', 'score')]:
        return True
    return False


def is_not_right_section(d):
    if d[0] == 'div' and ('class', 'tab-content visible-xs') in d[1]:
        return True
    return False


def is_right_section(d):
    if d[0] == 'div' and ('class', 'student-journal-lessons-table-holder hidden-xs') in d[1]:
        return True
    return False


def extract(s):
    return s.replace('\r', '').replace('\n', '').strip()


def process_home_task(s, buffer):
    if s[0] == 'a' and not s[1][0][1].startswith('http'):
        if buffer:
            buffer += ';'
        buffer += 'http://darit.space/dienasgramata/' + urllib.parse.quote(s[2].replace('\r', '').replace('\n', '').strip())
    else:
        if buffer:
            buffer += ';'
        buffer += s[2].replace('\r', '').replace('\n', '').strip()
    return buffer

# encode('utf-8').decode().


_date = ""
_day = ""
_subj = ""
_after_hometask = False
_hometask = ""

_right_section = False

db_records = []


def is_exists_hometask(_date, _day, _subj):
    if len(list(dienasgramata.find({"kind": "exercise", "date": f"{_date}", "day": f"{_day}", "subject": f"{_subj}"}))) > 0:
        return True
    return False


while True:
    try:
        myclient = pymongo.MongoClient(config["db.url"])

        with myclient:
            dienasgramata = myclient.school.dienasgramata

            data = request_site()
            i = 0
            while i <= len(data) - 1:
                d = data[i]
                # print(d)

                if is_right_section(d):
                    _right_section = True
                    i += 1
                    continue

                if not _right_section:
                    i += 1
                    continue

                if is_not_right_section(d):
                    break

                if is_date(d):
                    _d = extract(d[2])
                    _date = _d.split('. ')[0]
                    _day = _d.split('. ')[1]
                    _subj = ""
                    _hometask = ""
                    _after_hometask = False
                elif is_title(d):
                    _subj = extract(d[2])
                elif is_hometask(d):
                    _after_hometask = True
                elif is_after_hometask(d, _after_hometask):
                    _hometask = process_home_task(d, _hometask)
                elif is_score(d) and _hometask:
                    _after_hometask = False
                    if not is_exists_hometask(_date, _day, _subj):
                        db_records.append(build_db_record(_date, _day, _subj, _hometask))
                    _hometask = ""

                i += 1

            for i in db_records:
                print(i)
            if db_records:
                dienasgramata.insert_many(db_records)
            # json_to_file(config['export.file.path'], db_records)


    except RuntimeError as e:
        logger.error(e)

    if 'restart' in config and config['restart'] > 0:
        logger.info("Waiting %s seconds.", config['restart'])
        time.sleep(config['restart'])
    else:
        break
