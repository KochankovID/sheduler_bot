from datetime import datetime
from datetime import timedelta
from pprint import pprint
import requests


r = requests.get(
    url="https://portal.unn.ru/ruzapi/schedule/student/96414",
    params={
        "start": datetime.now().strftime('%Y-%m-%d'),
        "finish": datetime.now().strftime('%Y-%m-%d'),
        "lng": 1,
    },
)

lecture_str = '''
-----------------------------------
{st}-{en} {aud} {build}
{dis}
{type}
{lect}
-----------------------------------
'''

if r.status_code == 200:
    outputs = []
    data = r.json()
    for lesson in data:
        auditorium = lesson['auditorium']
        start_time = lesson['beginLesson']
        end_time = lesson['endLesson']
        les_type = lesson['kindOfWork']
        discipline = lesson['discipline']
        lecturer = lesson['lecturer']
        building = lesson['building']
        outputs.append(
            lecture_str.format(
                st=start_time,
                en=end_time,
                aud=auditorium,
                build=building,
                dis=discipline,
                type=les_type,
                lect=lecturer,
            )
        )

pprint(outputs)

r = requests.get(
    url="https://portal.unn.ru/ruzapi/schedule/student/96414",
    params={
        "start": (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d'),
        "finish": (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d'),
        "lng": 1,
    },
)

if r.status_code == 200:
    outputs = []
    data = r.json()
    for lesson in data:
        les_type = lesson['kindOfWork']
        discipline = lesson['discipline']
        outputs.append(
            discipline + ' ' + les_type
        )

results = '\n'.join(outputs)
if not results:
    results = 'пар нет, охуенно!'

tommorrow = 'Завтра:\n' + results
pprint(tommorrow)
