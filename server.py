from functools import partial
from json import dumps

from aiohttp import web

from main import process, Article

REQ_KEY = 'urls'
ERROR_MESSAGE_TEMPL = 'there are no "{}" key in query string'


async def process_urls(request: web.Request):
    value = request.query.get(REQ_KEY)
    if value is None:
        raise web.HTTPBadRequest(
            text=ERROR_MESSAGE_TEMPL.format(REQ_KEY)
        )

    urls = value.split(',')
    prepared_urls = [Article(url=url) for url in urls]
    result = await process(prepared_urls)
    return web.json_response(data=result, dumps=partial(dumps, indent=4))


def main():
    app = web.Application()
    app.add_routes([web.get('/', process_urls),
                    ])
    # Можно было бы задать порт как таске, но буду использовать дефолтный
    # Пока не прикрутил настройки
    web.run_app(app)


if __name__ == '__main__':
    main()
