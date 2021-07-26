import logging as log
import time
import zipfile
from typing import List
from enum import Enum
from urllib.parse import urlparse
import contextlib

import aiohttp
import asyncio
import pymorphy2
from anyio import create_task_group
from async_timeout import timeout

import adapters
import text_tools

CHARGED_DICT_ZIP = 'charged_dict.zip'
REQUEST_TIMEOUT_SEC = 1.5
TEST_ARTICLES = (
    ('https://inosmi.corrupted/politic/20210621/249959311.html',
     'corrupted',
     ),
    ('https://lenta.ru/news/2021/07/19/baidenhck/',
     'Байден рассказал о различии между российскими и китайскими кибератаками'
     ),
    ('https://ria.ru/20210719/rasizm-1741747346.html',
     'Гондурас победил Германию. И это только начало чудес'
     ),
    ('https://inosmi.ru/politic/20210621/249959311.html',
     'Нападение на Советский Союз 80 лет назад',
     ),
    ('https://inosmi.ru/politic/20210628/250000579.html',
     'Россия потребовала сдать оружие! Боевые самолеты начали полеты на малой высоте',
     ),
    ('https://inosmi.ru/politic/20210629/249997600.html',
     'Какое влияние имеет ускорение Россией дедолларизации?',
     ),
)

RESULT_TEMPLATE = """Заголовок: {title}
Статус: {status}
Рейтинг: {score}
Слов в статье: {words_count}
"""


class ProcessingStatus(Enum):
    OK = 'OK'
    FETCH_ERROR = 'FETCH_ERROR'
    PARSING_ERROR = 'PARSING_ERROR'
    TIMEOUT = 'TIMEOUT'


class LazyJaundiceException(Exception):
    pass


@contextlib.contextmanager
def log_time(name: str = ''):
    start = time.monotonic()
    try:
        yield
    finally:
        finish = time.monotonic()
    log.info('Анализ {} закончен за {:.2f} сек'.format(name, finish - start))


class LazyJaundice(object):
    _morph = None
    _charged_words = None

    def __init__(self):
        raise LazyJaundiceException('Do not instantiate this class')

    @classmethod
    def get_morph(cls):
        if cls._morph is None:
            cls._morph = pymorphy2.MorphAnalyzer()
        return cls._morph

    @classmethod
    def get_charged_words(cls):
        if cls._charged_words is None:
            cls._charged_words = []
            with zipfile.ZipFile(CHARGED_DICT_ZIP) as zf:
                for f_name in zf.namelist():
                    if not f_name.endswith('.txt'):
                        continue
                    with zf.open(f_name) as f:
                        cls._charged_words.extend(f.readlines())

            cls._charged_words = [
                word.decode('utf-8').strip()
                for word in cls._charged_words
            ]
            log.info("Слов: {}".format(len(cls._charged_words)))
        return cls._charged_words


async def fetch(session, url):
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


async def process_article(session,
                          morph,
                          charged_words,
                          result: List,
                          url,
                          title,
                          ):
    status: ProcessingStatus = ProcessingStatus.OK
    score: [float] = None
    words_count: [int] = None

    def append_to_result() -> None:
        result.append(RESULT_TEMPLATE.format(title=title,
                                             status=status.value,
                                             score=score,
                                             words_count=words_count,
                                             ))

    try:
        async with timeout(REQUEST_TIMEOUT_SEC):
            html = await fetch(session,
                               url)
    except aiohttp.ClientConnectorError:
        status = ProcessingStatus.FETCH_ERROR
        title = 'URL not exists'
        append_to_result()
        return
    except asyncio.TimeoutError:
        status = ProcessingStatus.TIMEOUT
        append_to_result()
        return

    try:
        cleaned_text = adapters.inosmi_ru.sanitize(html, plaintext=True)
    except adapters.ArticleNotFound:
        status = ProcessingStatus.PARSING_ERROR
        host = urlparse(url).hostname
        title = 'Статья на {}'.format(host)
        append_to_result()
        return

    with log_time(title):
        split_text = text_tools.split_by_words(morph, cleaned_text)

    score = text_tools.calculate_jaundice_rate(split_text, charged_words)
    words_count = len(split_text)
    append_to_result()


async def main():
    log.basicConfig(level=log.INFO)
    result = []
    async with aiohttp.ClientSession() as session:
        async with create_task_group() as tg:
            for article in TEST_ARTICLES:
                tg.start_soon(
                    process_article,
                    session,
                    LazyJaundice.get_morph(),
                    LazyJaundice.get_charged_words(),
                    result,
                    *article,
                )

    # не асинхронно как-то
    for res in result:
        print(res)


asyncio.run(main())
