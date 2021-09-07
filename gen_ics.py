from datetime import datetime
from datetime import timedelta
from typing import List

from furl import furl

from functools import lru_cache

import backoff
import requests
from environs import Env
from ics import Calendar, DisplayAlarm, Event
from pydantic import BaseModel

env = Env()
env.read_env()

CASHED_URLS = {
    'Численные методы': 'https://zoom.us/j/99222433992?pwd=eVVNRWZoKzhFNjVXN0dkOTdjNnVZUT09',
}


class Lesson(BaseModel):
    beginLesson: str
    endLesson: str
    auditorium: str
    building: str
    discipline: str
    kindOfWork: str
    lecturer: str
    dayOfWeek: str
    date: datetime

    @property
    def url(self):
        if self.kindOfWork != 'Лекция':
            return ''
        lesson_url = CASHED_URLS.get(self.discipline)
        return lesson_url or ''

    def dict(self, *args, **kwargs):
        result = super().dict(*args, **kwargs)
        return result | {'url': self.url}


class Day(BaseModel):
    date: datetime
    dayOfWeek: int
    lessons: List[Lesson]


class Schedule(BaseModel):
    days: List[Day]

    def get_all_lessons(self):
        lessons = []
        for day in self.days:
            lessons.extend(day.lessons)
        return lessons


class TelegrammClient:
    CHATS = {
        'production': '@unnschedule',
        'debug': '@debug_schedule_bot'
    }

    URL_TEMPLATE = 'https://api.telegram.org/'

    def __init__(self, token: str, debug: bool = True):
        self._base_url = furl(self.URL_TEMPLATE).add(path=f'bot{token}')
        self.debug = debug

    def send_message(self, text: str):
        data = {"text": text.encode("utf8"), "chat_id": self.chat_id}
        url = furl(self._base_url).add(path='sendMessage')
        responce = requests.post(url, data)
        responce.raise_for_status()

    def send_document(self, file_name: str):
        data = {"chat_id": self.chat_id}
        files = {'document': open(file_name, 'rb')}
        url = furl(self._base_url).add(path='sendDocument')
        responce = requests.post(url, data, files=files)
        responce.raise_for_status()

    @property
    def chat_id(self):
        if self.debug:
            return self.CHATS['debug']
        return self.CHATS['production']


class UNNClient:
    TEMPLATE_URL = 'https://portal.unn.ru/ruzapi/schedule/student/'

    def __init__(self, student_id: str):
        self._unn_url = furl(self.TEMPLATE_URL).add(path=student_id)

    @backoff.on_exception(backoff.expo, Exception, max_time=10)
    def get_schedule(self, start=datetime.now(), finish=datetime.now()) -> dict:
        responce = requests.get(
            url=self._unn_url,
            params={
                "start": start.strftime('%Y-%m-%d'),
                "finish": finish.strftime('%Y-%m-%d'),
                "lng": 1,
            },
        )
        responce.raise_for_status()
        return responce.json()


class Parcer:
    @classmethod
    def parce_schedule(cls, timetable: dict) -> Schedule:
        days = cls.split_on_days(timetable)
        return Schedule(
            days=[
                Day(
                    date=datetime.strptime(date, '%Y.%m.%d'),
                    dayOfWeek=lessons[0]['dayOfWeek'],
                    lessons=cls.parce_lessons(lessons)
                ) for date, lessons in days.items()
            ]
        )

    @staticmethod
    def parce_lessons(timetable: List[dict]) -> List[Lesson]:
        return [Lesson(
            beginLesson=lesson['beginLesson'],
            endLesson=lesson['endLesson'],
            auditorium=lesson['auditorium'],
            building=lesson['building'],
            discipline=lesson['discipline'],
            kindOfWork=lesson['kindOfWork'],
            lecturer=lesson['lecturer'],
            date=datetime.strptime('{lesson_date} {lesson_time}'.format(
                lesson_date=lesson['date'],
                lesson_time=lesson['beginLesson']), '%Y.%m.%d %H:%M'),
            dayOfWeek=lesson['dayOfWeek']
        ) for lesson in timetable]

    @staticmethod
    def split_on_days(timetable: dict):
        days = {}
        for lesson in timetable:
            date = lesson['date']
            if date not in days:
                days[date] = [lesson]
            else:
                days[date].append(lesson)
        return days


class MessageGenerator:
    WEEKDAY_MAPING = {
        1: ('пн', 'понедельник'),
        2: ('вт', 'вторник'),
        3: ('ср', 'среда'),
        4: ('чт', 'четверг'),
        5: ('пт', 'пятница'),
        6: ('сб', 'суббота'),
        7: ('вс', 'воскресенье'),
    }

    DAY_HEADER = '''------------{date}-------------
#{weekday} #{wdslug}'''

    LECTURE_HEADER = '''{beginLesson}-{endLesson} {auditorium} {building}'''

    LECTURE_STR = '''-----------------------------------
{discipline}
{kindOfWork}
{lecturer}{url}
-----------------------------------
'''

    @classmethod
    def full_schedule(cls, timetable: Schedule) -> str:
        day_messages = cls.schedule_per_day(timetable)
        return '\n\n'.join(day_messages)

    @classmethod
    def schedule_per_day(cls, timetable: Schedule) -> List[str]:
        return [cls.day_with_header(day) for day in timetable.days]

    @classmethod
    def day_with_header(cls, day: Day) -> str:
        day_message = cls.day(day)
        return cls.add_header_date(day_message, day.date, day.dayOfWeek)

    @classmethod
    def day(cls, day: Day) -> str:
        lesson_messages = []
        for lesson in day.lessons:
            string_lesson = cls.LECTURE_HEADER.format(**lesson.dict())
            string_lesson += cls.LECTURE_STR.format(
                discipline=lesson.discipline,
                kindOfWork=lesson.kindOfWork,
                lecturer=lesson.lecturer,
                url=f'\n\n{lesson.url}' if lesson.url else '',
            )
            lesson_messages.append(string_lesson)

        response = ''.join(lesson_messages)
        if not response:
            response = 'Пар нет, очешуенно!\n\n'
        return response

    @classmethod
    def add_header_date(cls, message: str, date: datetime, weekday: int):
        date_str = date.strftime('%Y.%m.%d')
        wdslug, weekday_name = cls.WEEKDAY_MAPING[weekday]
        return cls.DAY_HEADER.format(date=date_str, weekday=weekday_name, wdslug=wdslug) + '\n' + message


class IcsGenerator:
    LECTURE_LOCATION = '{auditorium} {building}'

    LECTURE_STR = '''{discipline}
{kindOfWork}
{lecturer}
{url}'''

    TIMEZONE_CORRECTION = timedelta(hours=3)

    LESSON_DURATION = timedelta(minutes=90)

    @classmethod
    def ics(cls, timetable: Schedule):
        calendar = Calendar()
        events = [Event(
            name=lesson.discipline,
            created=datetime.now(),
            location=cls.LECTURE_LOCATION.format(**lesson.dict()),
            begin=lesson.date - cls.TIMEZONE_CORRECTION,
            end=lesson.date + cls.LESSON_DURATION - cls.TIMEZONE_CORRECTION,
            description=cls.LECTURE_STR.format(**lesson.dict()),
            alarms=[
                DisplayAlarm(trigger=timedelta(minutes=15))
            ] if lesson.discipline != 'Военная подготовка' else []
        ) for lesson in timetable.get_all_lessons()]

        calendar.events.update(events)
        return calendar


class ScheduleBot:
    def __init__(self, client_id: str, token: str, debug: bool = True):
        self.telegramm = TelegrammClient(token, debug)
        self.unn = UNNClient(client_id)

    def send_schedule_per_day(self, start: datetime):
        timetable = self.get_schedule(start)
        messages = MessageGenerator.schedule_per_day(timetable)
        for message in messages:
            try:
                self.telegramm.send_message(message)
            except RuntimeError as e:
                print(str(e))
                return {"statusCode": 500, "body": str(e)}

        return {"statusCode": 200, "body": "complete"}

    def send_ics(self, start: datetime):
        timetable = self.get_schedule(start)
        ics = IcsGenerator.ics(timetable)

        with open('my.ics', 'w') as f:
            f.write(str(ics))

        try:
            self.telegramm.send_document('my.ics')
        except RuntimeError as e:
            print(str(e))
            return {"statusCode": 500, "body": str(e)}

        return {"statusCode": 200, "body": "complete"}

    @lru_cache
    def get_schedule(self, start: datetime) -> Schedule:
        raw_timetable = self.unn.get_schedule(finish=start + timedelta(days=6))
        return Parcer.parce_schedule(raw_timetable)


# if __name__ == '__main__':
#     client = '125633'
#     TOKEN = env('TELEGRAM_TOKEN')
#     schedule_bot = ScheduleBot(client, TOKEN)
#     schedule_bot.send_schedule_per_day(datetime.now())
#     schedule_bot.send_ics(datetime.now())


def schedule_event(event, context):
    event_date = datetime.strptime(event['time'], '%Y-%m-%dT%H:%M:%SZ')
    client = '125633'
    token = env('TELEGRAM_TOKEN')
    schedule_bot = ScheduleBot(client, token)
    schedule_bot.send_schedule_per_day(event_date)
    schedule_bot.send_ics(event_date)
