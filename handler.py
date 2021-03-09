import os
import re
import sys
from datetime import datetime
from datetime import timedelta
from typing import List

here = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(here, "./vendored"))

import requests
from pydantic import BaseModel
from environs import Env


env = Env()
env.read_env()

TOKEN = env('TELEGRAM_TOKEN')
BASE_URL = "https://api.telegram.org/bot{}".format(TOKEN)

lecture_str = '''-----------------------------------
{beginLesson}-{endLesson} {auditorium} {building}
{discipline}
{kindOfWork}
{lecturer}{url}
-----------------------------------
'''

annonce_str = '{discipline} {kindOfWork}'

chats = {'prod': '@unnschedule', 'dev': '@debug_schedule_bot'}
unn_url = 'https://portal.unn.ru/ruzapi/schedule/student/96414'

cashed_urls = {
    'Параллельное программирование': 'https://teams.microsoft.com/dl/launcher/launcher.html?url=%2F_%23%2Fl%2Fmeetup-join%2F19%3Ameeting_NDQ5ZDAyNjUtMThkYS00MzU0LWJhYmYtYmE2NGI1ZWM5YTY3%40thread.v2%2F0%3Fcontext%3D%257b%2522Tid%2522%253a%252260b6ee4f-43c2-4c1f-b509-d6fad245297a%2522%252c%2522Oid%2522%253a%25225296e582-edba-4b94-ba1f-ca426c653e15%2522%257d%26anon%3Dtrue&type=meetup-join&deeplinkId=c84d99bb-1c02-4b48-8366-79ef205b5a6a&directDl=true&msLaunch=true&enableMobilePage=true&suppressPrompt=true',
    'Теория вероятностей и математическая статистика': 'https://us02web.zoom.us/j/7962245085?pwd=WW5OMEczN2Vsc21qem1rYnlvaSt2QT09'
}


def schedule(event, context):
    if event.get('source') and event['source'] == 'aws.events':
        event_date = datetime.strptime(event['time'], '%Y-%m-%dT%H:%M:%SZ')

        chat_id = chats['prod']

        today_schedule = get_schedule(start=event_date, finish=event_date)

        today_lessons_str = []
        for lesson in today_schedule.lessons:
            url = cashed_urls.get(lesson.discipline)
            url = '\n\n' + url if (url and lesson.kindOfWork == 'Лекция') else ''
            string_lesson = lecture_str.format(url=url, **lesson.dict())
            today_lessons_str.append(string_lesson)
        response = ''.join(today_lessons_str)
        if not response:
            response = 'Пар нет, очешуенно!\n\n'
        response = event_date.strftime('%Y-%m-%d') + '\n\n' + response

        tommorrow_schedule = get_schedule(
            start=event_date+ timedelta(days=1),
            finish=event_date + timedelta(days=1),
        )

        annonces = (
            annonce_str.format(**lesson.dict()) for lesson in tommorrow_schedule.lessons
        )
        annonces_formatted = '\n'.join(annonces)
        if not annonces_formatted:
            annonces_formatted = 'Пар нет, чилим!'

        annonces_formatted = 'Завтра:\n' + annonces_formatted
        response += annonces_formatted

        try:
            send_message(response, chat_id)
        except RuntimeError as e:
            print(str(e))
            return {"statusCode": 500, "body": str(e)}

        return {"statusCode": 200, "body": "complete"}

    return {"statusCode": 500, "body": "Wrong event!"}


def get_schedule(
    url=unn_url,
    start=datetime.now(),
    finish=datetime.now(),
):
    r = requests.get(
        url=unn_url,
        params={
            "start": start.strftime('%Y-%m-%d'),
            "finish": finish.strftime('%Y-%m-%d'),
            "lng": 1,
        },
    )

    if r.status_code == 200:
        lessons = []
        data = r.json()
        for raw_lesson in data:
            lessons.append(Lesson(**raw_lesson))
        return Schedule(start_date=start, end_date=finish, lessons=lessons)


class Lesson(BaseModel):
    beginLesson: str
    endLesson: str
    auditorium: str
    building: str
    discipline: str
    kindOfWork: str
    lecturer: str


class Schedule(BaseModel):
    start_date: datetime
    end_date: datetime
    lessons: List[Lesson]


def send_message(text: str, chat_id: str):
    data = {"text": text.encode("utf8"), "chat_id": chat_id}
    url = BASE_URL + "/sendMessage"
    r = requests.post(url, data)
    if r.status_code != 200:
        print(text)
        raise RuntimeError(str(r))