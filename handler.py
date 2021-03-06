import os
import sys
from datetime import datetime
from datetime import timedelta


here = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(here, "./vendored"))


from environs import Env

env = Env()
env.read_env()


import requests

TOKEN = env('TELEGRAM_TOKEN')
BASE_URL = "https://api.telegram.org/bot{}".format(TOKEN)

lecture_str = '''-----------------------------------
{st}-{en} {aud} {build}
{dis}
{type}
{lect}
-----------------------------------
'''


def hello(event, context):
    if event.get('detail-type'):
        chat_id = '@unnschedule'

        r = requests.get(
            url="https://portal.unn.ru/ruzapi/schedule/student/96414",
            params={
                "start": datetime.now().strftime('%Y-%m-%d'),
                "finish": datetime.now().strftime('%Y-%m-%d'),
                "lng": 1,
            },
        )

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

        response = ''.join(outputs)
        if not response:
            response = 'Пар нет, заебись!'
        response = datetime.now().strftime('%Y-%m-%d') + '\n\n' + response

        r = requests.get(
            url="https://portal.unn.ru/ruzapi/schedule/student/96414",
            params={
                "start": (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
                "finish": (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
                "lng": 1,
            },
        )

        if r.status_code == 200:
            outputs = []
            data = r.json()
            for lesson in data:
                les_type = lesson['kindOfWork']
                discipline = lesson['discipline']
                outputs.append(discipline + ' ' + les_type)

        results = '\n'.join(outputs)
        if not results:
            results = 'Пар нет, охуенно!'

        tommorrow = 'Завтра:\n' + results
        
        response += tommorrow

        data = {"text": response.encode("utf8"), "chat_id": chat_id}
        url = BASE_URL + "/sendMessage"

        r = requests.post(url, data)
        if r.status_code != 200:
            print(r)
            return {"statusCode": 500, "body": r.text}

    return {"statusCode": 200, "body": "complete"}
