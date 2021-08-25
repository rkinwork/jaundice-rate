from functools import partial
from json import dumps
from dataclasses import asdict

from aiohttp import web

from main import process, Article

REQ_KEY = 'urls'
ERROR_MESSAGE_TEMPLATE = 'there are no "{}" key in query string'
MAX_URLS_COUNT = 10
ERROR_MESSAGE_COUNT = f'too many urls in request, ' \
                      f'should be {MAX_URLS_COUNT} or less'


def prepare_error(error_txt: str):
    return dumps({'error': error_txt})


async def process_urls(request: web.Request):
    value = request.query.get(REQ_KEY)
    if value is None:
        raise web.HTTPBadRequest(
            text=prepare_error(
                error_txt=ERROR_MESSAGE_TEMPLATE.format(REQ_KEY),
            ),
            content_type='application/json',
        )

    urls = value.split(',')
    if len(urls) > MAX_URLS_COUNT:
        raise web.HTTPBadRequest(
            text=prepare_error(
                error_txt=ERROR_MESSAGE_COUNT,
            ),
            content_type='application/json',
        )
    prepared_urls = [Article(url=url) for url in urls]
    results = await process(prepared_urls)
    results = [asdict(result_el) for result_el  in results]
    return web.json_response(data=results, dumps=partial(dumps, indent=4))


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
