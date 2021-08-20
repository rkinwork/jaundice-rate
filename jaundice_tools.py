import logging as log
import time
import zipfile
from typing import List, NamedTuple, Optional
from enum import Enum
from urllib.parse import urlparse
import contextlib

import aiohttp
import asyncio
import pymorphy2
from async_timeout import timeout
import pytest

import adapters
import text_tools

CHARGED_DICT_ZIP = 'charged_dict.zip'
REQUEST_TIMEOUT_SEC = 10

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


class Article(NamedTuple):
    url: str
    title: Optional[str] = None


class Result(NamedTuple):
    status: str
    url: str
    score: Optional[float] = None
    words_count: Optional[int] = None
    title: Optional[str] = None


class DataBlock(NamedTuple):
    article: Article
    expected: Result
    request_timeout_sec: Optional[float] = None


DATA_TESTS = (
    DataBlock(
        Article('https://inosmi.corrupted/politic/20210621/249959311.html',
                'corrupted',
                ),
        Result(
            status=ProcessingStatus.FETCH_ERROR.value,
            url='https://inosmi.corrupted/politic/20210621/249959311.html',
            title='URL not exists'
        ),
    ),
    DataBlock(
        Article('https://lenta.ru/news/2021/07/19/baidenhck/',
                'Байден рассказал о различии между '
                'российскими и китайскими кибератаками',
                ),
        Result(
            status=ProcessingStatus.PARSING_ERROR.value,
            url='https://lenta.ru/news/2021/07/19/baidenhck/',
            title='Статья на lenta.ru',
        ),

    ),
    DataBlock(
        Article('https://ria.ru/20210719/rasizm-1741747346.html',
                'Гондурас победил Германию. И это только начало чудес'
                ),
        Result(
            status=ProcessingStatus.PARSING_ERROR.value,
            url='https://ria.ru/20210719/rasizm-1741747346.html',
            title='Статья на ria.ru'
        ),

    ),
    DataBlock(

        Article('https://inosmi.ru/politic/20210621/249959311.html',
                'Нападение на Советский Союз 80 лет назад',
                ),
        Result(
            status=ProcessingStatus.OK.value,
            url='https://inosmi.ru/politic/20210621/249959311.html',
            title='Нападение на Советский Союз 80 лет назад',
        ),

    ),
    DataBlock(

        Article('https://inosmi.ru/politic/20210628/250000579.html',
                'Россия потребовала сдать оружие! Боевые самолеты начали полеты на малой высоте',
                ),
        Result(
            status=ProcessingStatus.OK.value,
            url='https://inosmi.ru/politic/20210628/250000579.html',
            title='Россия потребовала сдать оружие! Боевые самолеты начали полеты на малой высоте',
        ),

    ),
    DataBlock(

        Article('https://inosmi.ru/politic/20210629/249997600.html',
                'Какое влияние имеет ускорение Россией дедолларизации?',
                ),
        Result(
            status=ProcessingStatus.OK.value,
            url='https://inosmi.ru/politic/20210629/249997600.html',
            title='Какое влияние имеет ускорение Россией дедолларизации?',
        ),

    ),
    DataBlock(

        Article('https://inosmi.ru/politic/20210629/249997600.html',
                'Какое влияние имеет ускорение Россией дедолларизации?',
                ),
        Result(
            status=ProcessingStatus.TIMEOUT.value,
            url='https://inosmi.ru/politic/20210629/249997600.html',
            title='Какое влияние имеет ускорение Россией дедолларизации?',
        ),
        request_timeout_sec=0.1

    ),
)


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
                          result: List[Result],
                          url,
                          title,
                          request_timeout_sec=None,
                          ):
    request_timeout_sec = request_timeout_sec or REQUEST_TIMEOUT_SEC
    status: ProcessingStatus = ProcessingStatus.OK
    score: [float] = None
    words_count: [int] = None

    def append_to_result() -> None:
        result.append(Result(
            **{
                'status': status.value,
                'url': url,
                'score': score,
                'words_count': words_count,
                'title': title,
            },
        )
        )

    try:
        async with timeout(request_timeout_sec):
            html = await fetch(session,
                               url)
    except (aiohttp.ClientConnectorError, aiohttp.InvalidURL):
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


@pytest.fixture()
def morph_instance():
    return LazyJaundice.get_morph()


@pytest.fixture()
def charged_words():
    return LazyJaundice.get_charged_words()


@pytest.fixture(params=DATA_TESTS)
def urls(request):
    return request.param


async def process_test(urls, charged_words, morph_instance, result):
    async with aiohttp.ClientSession() as session:
        await process_article(
            session=session,
            morph=morph_instance,
            charged_words=charged_words,
            url=urls.article.url,
            result=result,
            title=urls.article.title,
            request_timeout_sec=urls.request_timeout_sec,
        )


def test_process_article(urls: DataBlock, charged_words, morph_instance):
    result = []
    asyncio.run(process_test(
        urls=urls,
        charged_words=charged_words,
        morph_instance=morph_instance,
        result=result,
    )
    )
    assert len(result) == 1
    result = result[0]
    assert result.status == urls.expected.status
    assert result.title == urls.expected.title
    assert result.url == urls.expected.url
