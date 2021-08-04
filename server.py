from functools import partial
from json import dumps

from aiohttp import web

REQ_KEY = 'urls'
ERROR_MESSAGE_TEMPL = 'there are no "{}" key in query string'


async def handle(request: web.Request):
    value = request.query.get(REQ_KEY)
    if value is None:
        raise web.HTTPBadRequest(
            text=ERROR_MESSAGE_TEMPL.format(REQ_KEY)
        )

    res = {
        REQ_KEY: value.split(',')
    }

    return web.json_response(data=res, dumps=partial(dumps, indent=4))


def main():
    app = web.Application()
    app.add_routes([web.get('/', handle),
                    ])
    # Можно было бы задать порт как таске, но буду использовать дефолтный
    web.run_app(app)


if __name__ == '__main__':
    main()
