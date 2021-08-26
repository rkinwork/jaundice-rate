import logging as log
import time
import zipfile
from typing import List, NamedTuple, Optional
from enum import Enum
from urllib.parse import urlparse
import contextlib
from dataclasses import dataclass

import aiohttp
import asyncio
import pymorphy2
from async_timeout import timeout
import pytest

import adapters
import text_tools

CHARGED_DICT_ZIP = 'charged_dict.zip'
REQUEST_TIMEOUT_SEC = 10

RESPONSE_TEMPLATE = """Заголовок: {title}
Статус: {status}
Рейтинг: {score}
Слов в статье: {words_count}
"""


class ProcessingStatus(Enum):
    OK = 'OK'
    FETCH_ERROR = 'FETCH_ERROR'
    PARSING_ERROR = 'PARSING_ERROR'
    TIMEOUT = 'TIMEOUT'


class JaundiceToolsException(Exception):
    pass


class RawArticle(NamedTuple):
    url: str
    title: Optional[str] = None


@dataclass
class Article:
    status: str
    url: str
    score: Optional[float] = None
    words_count: Optional[int] = None
    title: Optional[str] = None


class DataBlock(NamedTuple):
    article: RawArticle
    expected: Article
    request_timeout_sec: Optional[float] = None


DATA_TESTS = (
    DataBlock(
        RawArticle('https://inosmi.corrupted/politic/20210621/249959311.html',
                   'corrupted',
                   ),
        Article(
            status=ProcessingStatus.FETCH_ERROR.value,
            url='https://inosmi.corrupted/politic/20210621/249959311.html',
            title='URL not exists'
        ),
    ),
    DataBlock(
        RawArticle('https://lenta.ru/news/2021/07/19/baidenhck/',
                   'Байден рассказал о различии между '
                   'российскими и китайскими кибератаками',
                   ),
        Article(
            status=ProcessingStatus.PARSING_ERROR.value,
            url='https://lenta.ru/news/2021/07/19/baidenhck/',
            title='Статья на lenta.ru',
        ),

    ),
    DataBlock(
        RawArticle('https://ria.ru/20210719/rasizm-1741747346.html',
                   'Гондурас победил Германию. И это только начало чудес'
                   ),
        Article(
            status=ProcessingStatus.PARSING_ERROR.value,
            url='https://ria.ru/20210719/rasizm-1741747346.html',
            title='Статья на ria.ru'
        ),

    ),
    DataBlock(

        RawArticle('https://inosmi.ru/politic/20210621/249959311.html',
                   'Нападение на Советский Союз 80 лет назад',
                   ),
        Article(
            status=ProcessingStatus.OK.value,
            url='https://inosmi.ru/politic/20210621/249959311.html',
            title='Нападение на Советский Союз 80 лет назад',
        ),

    ),
    DataBlock(

        RawArticle('https://inosmi.ru/politic/20210628/250000579.html',
                   'Россия потребовала сдать оружие! Боевые самолеты начали полеты на малой высоте',
                   ),
        Article(
            status=ProcessingStatus.OK.value,
            url='https://inosmi.ru/politic/20210628/250000579.html',
            title='Россия потребовала сдать оружие! Боевые самолеты начали полеты на малой высоте',
        ),

    ),
    DataBlock(

        RawArticle('https://inosmi.ru/politic/20210629/249997600.html',
                   'Какое влияние имеет ускорение Россией дедолларизации?',
                   ),
        Article(
            status=ProcessingStatus.OK.value,
            url='https://inosmi.ru/politic/20210629/249997600.html',
            title='Какое влияние имеет ускорение Россией дедолларизации?',
        ),

    ),
    DataBlock(

        RawArticle('https://inosmi.ru/politic/20210629/249997600.html',
                   'Какое влияние имеет ускорение Россией дедолларизации?',
                   ),
        Article(
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


class JaundiceTools(object):
    _morph = None
    _charged_words = None

    def __init__(self):
        raise JaundiceToolsException('Do not instantiate this class')

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
                        words = [line.decode('utf-8').strip() for line in f]
                        cls._charged_words = words

            if len(cls._charged_words) == 0:
                raise JaundiceToolsException('Empty charged words dict file')
            log.info('Слов: {}'.format(len(cls._charged_words)))
        return cls._charged_words

    @staticmethod
    async def fetch(session, url):
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.text()


async def process_article(session,
                          morph,
                          charged_words,
                          result: List[Article],
                          url,
                          title,
                          request_timeout_sec=REQUEST_TIMEOUT_SEC,
                          ):
    # хотя и в ревью было замечание избавится от return
    # не хотелось усложнять flow и всю обработку запихивать в один try
    # И если грохнется выполнение - то гарантированно уже будет какой-то ответ
    article = Article(
        status=ProcessingStatus.FETCH_ERROR.value,
        url=url,
        title=title
    )
    result.append(article)

    try:
        async with timeout(request_timeout_sec):
            html = await JaundiceTools.fetch(session, url)
    except (aiohttp.ClientConnectorError, aiohttp.InvalidURL):
        article.status = ProcessingStatus.FETCH_ERROR.value
        article.title = 'URL not exists'
        return
    except asyncio.TimeoutError:
        article.status = ProcessingStatus.TIMEOUT.value
        return

    try:
        cleaned_text = adapters.inosmi_ru.sanitize(html, plaintext=True)
    except adapters.ArticleNotFound:
        article.status = ProcessingStatus.PARSING_ERROR.value
        host = urlparse(url).hostname
        article.title = 'Статья на {}'.format(host)
        return

    with log_time(title):
        words = await text_tools.split_by_words(morph, cleaned_text)

    article.score = text_tools.calculate_jaundice_rate(
        words,
        charged_words,
    )
    article.words_count = len(words)
    article.status = ProcessingStatus.OK.value


@pytest.fixture()
def morph_instance():
    return JaundiceTools.get_morph()


@pytest.fixture()
def charged_words():
    return JaundiceTools.get_charged_words()


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
    article = []
    asyncio.run(process_test(
        urls=urls,
        charged_words=charged_words,
        morph_instance=morph_instance,
        result=article,
    )
    )
    assert len(article) == 1
    article = article[0]
    assert article.status == urls.expected.status
    assert article.title == urls.expected.title
    assert article.url == urls.expected.url
