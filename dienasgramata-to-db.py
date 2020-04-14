#!/usr/bin/env python3
import logging
import urllib.parse
import time
import datetime
import json
from kafka import KafkaProducer
import pymongo
from bson import ObjectId

from utils import json_from_file, MyHTMLParser, _get, json_to_file

config_file_name = 'config.json'
config = {}

try:
    config = json_from_file(config_file_name, "Can't open ss-config file.")
except RuntimeError as e:
    print(e)
    exit()

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.strftime("%d.%m.%Y")
        return json.JSONEncoder.default(self, o)

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

producer = KafkaProducer(bootstrap_servers=[config['kafka.host']], value_serializer = lambda x: json.dumps(x, cls = JSONEncoder).encode('utf-8'))


def request_site():
    d = []
    try:
        for url in config["sites"]:
            parser_config = {'valid_tags': ['tr', 'td', 'a', 'b', 'span', 'div', 'h2']}
            d += MyHTMLParser(parser_config).feed_and_return(_get(url).content.decode()).data
    except RuntimeError as e:
        logger.debug(e)
    return d


def build_db_record(_date, _day, _subj, _tema, _hometask):
    try:
        a = {"kind": "exercise", "date": _date, "day": _day, "subject": _subj, "tema": _tema, "exercise": _hometask}
        return a
    except RuntimeError as e:
        logger.debug(e)
    return {}


def is_title(d):
    if d[0] == 'span' and d[1] == [('class', 'title')] and len(d) > 2 and extract(d[2]):
        return True
    return False


def is_date(d):
    if d[0] == 'h2' and d[1] == [] and len(d) > 2 and extract(d[2]):
        return True
    return False


def is_tema(d):
    if d[0] == 'td' and d[1] == [('class', 'subject')]:
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
        try:
            if buffer:
                buffer += ';'
            buffer += 'http://darit.space/dienasgramata/' + urllib.parse.quote(s[1][0][1].replace('\r', '').replace('\n', '').strip())
        except RuntimeError as e:
            logger.error(e)
    else:
        try:
            txt = s[2].replace('\r', '').replace('\n', '').strip()
            if txt:
                if buffer:
                    buffer += ';'
                buffer += txt
        except RuntimeError as e:
            logger.error(e)
    return buffer

# encode('utf-8').decode().


_date = ""
_day = ""
_subj = ""
_hometask_goingon = False
_hometask = ""
_tema = ""
_tema_goingon = False
_right_section = False

db_records = []


def get_db_record(_date, _day, _subj):
    _records = list(dienasgramata.find({"kind": "exercise", "date": _date , "day": f"{_day}", "subject": f"{_subj}"}))
    if len(_records) > 0:
        return _records[0]
    return None


def prepare_date(_d):
    _date_left = _d.split('. ')[0].split('.')
    _date_right = _d.split('. ')[1]
    return datetime.datetime(int(_date_left[2])+2000, int(_date_left[1]), int(_date_left[0])), _date_right


def notify(result):
    if producer:
        producer.send(config['kafka.topic'], value = {config["kafka.message.tag"]: result.inserted_ids})


def get_record(db_records, param):
    for r in db_records:
        if r['date'] == param['date'] and r['day'] == param['day'] and r['subject'] == param['subject']:
            return r
    return None


def add(db_records, param):
    r = get_record(db_records, param)
    if not r:
        db_records.append(param)
    else:
        if param['tema']:
            if r['tema']:
                r['tema'] = r['tema'] +'; '+ param['tema']
            else:
                r['tema'] = param['tema']
        if param['exercise']:
            if r['exercise']:
                r['exercise'] = r['exercise'] +'; '+ param['exercise']
            else:
                r['exercise'] = param['exercise']


while True:
    try:
        myclient = pymongo.MongoClient(config["db.url"])

        with myclient:
            dienasgramata = myclient.school.dienasgramata

            data = request_site()
            i = -1
            while i < len(data) - 1:
                i += 1
                d = data[i]
                # print(d)

                if is_right_section(d):
                    _right_section = True
                    continue

                if not _right_section:
                    continue

                if is_not_right_section(d):
                    _right_section = False
                    continue

                if is_date(d):
                    _date, _day = prepare_date(extract(d[2]))
                    _subj = ""
                    _hometask = ""
                    _tema = ""
                    _hometask_goingon = False
                    continue

                if is_title(d):
                    _subj = extract(d[2])
                    _hometask = ""
                    _hometask_goingon = False
                    continue

                if is_tema(d):
                    _tema_goingon = True
                    _tema = ""

                if is_hometask(d):
                    _tema = _hometask
                    _hometask = ""
                    _tema_goingon = False
                    _hometask_goingon = True

                if _subj and (_hometask_goingon or _tema_goingon):
                    if is_score(d) and (_hometask or _tema):
                        _hometask_goingon = False
                        r = get_db_record(_date, _day, _subj)
                        if not r:
                            add(db_records, build_db_record(_date, _day, _subj, _tema, _hometask))

                        _hometask = ""
                    else:
                        _hometask = process_home_task(d, _hometask)

            for i in db_records:
                print(i)
            if db_records:
                result = dienasgramata.insert_many(db_records)
                notify(result)
                db_records = []

    except RuntimeError as e:
        logger.error(e)
        db_records = []

    if 'restart' in config and config['restart'] > 0:
        logger.info("Waiting %s seconds.", config['restart'])
        time.sleep(config['restart'])
    else:
        break
