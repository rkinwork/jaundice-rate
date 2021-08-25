import logging as log
from typing import Iterable, List
from dataclasses import asdict

import aiohttp
import asyncio
from anyio import create_task_group

from jaundice_tools import Article, JaundiceTools, process_article
from jaundice_tools import DATA_TESTS, RESULT_TEMPLATE, Result


async def process(links: Iterable[Article]) -> List[Result]:
    result = []
    async with aiohttp.ClientSession() as session:
        async with create_task_group() as tg:
            for article in links:
                tg.start_soon(
                    process_article,
                    session,
                    JaundiceTools.get_morph(),
                    JaundiceTools.get_charged_words(),
                    result,
                    article.url,
                    article.title,
                )
    return result


async def main():
    log.basicConfig(level=log.INFO)
    test_articles = [el[0] for el in DATA_TESTS]
    results = await process(test_articles)
    # не асинхронно как-то
    for article_res in results:
        print(RESULT_TEMPLATE.format(**asdict(article_res)))


if __name__ == '__main__':
    asyncio.run(main())
