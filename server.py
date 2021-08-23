from functools import partial
from json import dumps

from aiohttp import web

from main import process, Article

REQ_KEY = 'urls'
ERROR_MESSAGE_TEMPL = 'there are no "{}" key in query string'
MAX_URLS_CNT = 10
ERROR_MESSAGE_CNT = 'too many urls in request, should be {} or less'.format(
    MAX_URLS_CNT
)


def prepare_error(error_txt: str):
    return dumps({'error': error_txt})


async def process_urls(request: web.Request):
    value = request.query.get(REQ_KEY)
    if value is None:
        raise web.HTTPBadRequest(
            text=prepare_error(
                error_txt=ERROR_MESSAGE_TEMPL.format(REQ_KEY),
            ),
            content_type='application/json',
        )

    urls = value.split(',')
    if len(urls) > MAX_URLS_CNT:
        raise web.HTTPBadRequest(
            text=prepare_error(
                error_txt=ERROR_MESSAGE_CNT,
            ),
            content_type='application/json',
        )
    prepared_urls = [Article(url=url) for url in urls]
    result = await process(prepared_urls)
    result = [el._asdict() for el in result]
    return web.json_response(data=result, dumps=partial(dumps, indent=4))


def main():
    app = web.Application()
    app.add_routes([web.get('/', process_urls),
                    ])
    # Можно было бы задать порт как в таске, но буду использовать дефолтный
    # Пока не прикрутил настройки
    web.run_app(app)


if __name__ == '__main__':
    main()
