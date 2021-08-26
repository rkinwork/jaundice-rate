import logging as log
from typing import Iterable, List
from dataclasses import asdict

import aiohttp
import asyncio
from anyio import create_task_group

from jaundice_tools import RawArticle, JaundiceTools, process_article
from jaundice_tools import DATA_TESTS, RESPONSE_TEMPLATE, Article


async def process(raw_articles: Iterable[RawArticle]) -> List[Article]:
    articles = []
    async with aiohttp.ClientSession() as session:
        async with create_task_group() as tg:
            for raw_article in raw_articles:
                tg.start_soon(
                    process_article,
                    session,
                    JaundiceTools.get_morph(),
                    JaundiceTools.get_charged_words(),
                    articles,
                    raw_article.url,
                    raw_article.title,
                )
    return articles


async def process_links():
    log.basicConfig(level=log.INFO)
    test_articles = [el[0] for el in DATA_TESTS]
    articles = await process(test_articles)
    # не асинхронно как-то
    for article in articles:
        print(RESPONSE_TEMPLATE.format(**asdict(article)))


def main():
    asyncio.run(process_links())


if __name__ == '__main__':
    main()
