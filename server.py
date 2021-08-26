from functools import partial
from json import dumps
from dataclasses import asdict

from aiohttp import web

from main import process, RawArticle

URLS_KEY = 'urls'
NO_URLS_ERROR_MESSAGE = f'there is no "{URLS_KEY}" key in query string'
MAX_URLS_COUNT = 10
MAX_URLS_COUNT_ERROR_MESSAGE = f'too many urls in request, ' \
                      f'should be {MAX_URLS_COUNT} or less'


def send_error(error_text: str):
    raise web.HTTPBadRequest(
        text=dumps({'error': error_text}),
        content_type='application/json',
    )


async def process_urls(request: web.Request):
    raw_urls = request.query.get(URLS_KEY)
    if raw_urls is None:
        send_error(NO_URLS_ERROR_MESSAGE)

    urls = raw_urls.split(',')
    if len(urls) > MAX_URLS_COUNT:
        send_error(MAX_URLS_COUNT_ERROR_MESSAGE)

    raw_articles = [RawArticle(url=url) for url in urls]
    articles = await process(raw_articles)
    return web.json_response(
        data=[asdict(article) for article in articles],
        dumps=partial(dumps, indent=4),
    )


def main():
    app = web.Application()
    app.add_routes(
        [
            web.get('/', process_urls),
        ],
    )
    # Можно было бы задать порт как в таске, но буду использовать дефолтный
    # Пока не прикрутил настройки
    web.run_app(app)


if __name__ == '__main__':
    main()
