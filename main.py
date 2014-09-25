import os
import logging
import hashlib

from tornado.web import RequestHandler
from tornado.web import URLSpec
from tornado.options import define
from tornado.options import parse_command_line
from tornado.options import options
from tornado.web import Application
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.httpclient import AsyncHTTPClient
from tornado.httpclient import HTTPError
from tornado.web import asynchronous
from tornado import gen

import redis

CACHE_TIME = 60

http_client = AsyncHTTPClient()

class IndexHandler(RequestHandler):
    def get(self):
        self.render('index.html')

class ProxyHandler(RequestHandler):
    @asynchronous
    @gen.engine
    def get(self):
        referer = self.request.headers.get('Referer')
        logging.debug('TODO: check referer %s' % referer)
        maps = {
            'fonts.twinsant.com': 'fonts.googleapis.com',
            'themes.twinsant.com': 'fonts.gstatic.com',
        }
        url = 'http://%s%s' % (maps[self.request.host], self.request.uri)

        @gen.engine
        def fetch_content(url, callback=None):
            key = hashlib.md5(url).hexdigest()
            content_type = self.application.redis.get(self.get_key(key, 'content_type'))
            content = self.application.redis.get(self.get_key(key, 'content'))
            if content_type is None or content is None:
                logging.debug('%s: Fetching %s ...' % (key, url))
                response = yield gen.Task(http_client.fetch, url, connect_timeout=60.0, request_timeout=60.0)
                if response.code == 200:
                    content_type = response.headers.get('Content-Type')
                    self.application.redis.set(self.get_key(key, 'content_type'), content_type)
                    self.application.redis.expire(self.get_key(key, 'content_type'), CACHE_TIME)
                    self.application.redis.set(self.get_key(key, 'content'), response.body)
                    self.application.redis.expire(self.get_key(key, 'content'), CACHE_TIME)
                    callback(response.body, content_type)
                else:
                    raise HTTPError(response.code)
            else:
                callback(content, content_type)

        ret, foo = yield gen.Task(fetch_content, url)
        content = ret[0]
        content_type = ret[1]
        if self.request.host == 'fonts.twinsant.com':
            html = content.replace('http://fonts.gstatic.com', 'http://themes.twinsant.com')
            self.write(html)
        if self.request.host == 'themes.twinsant.com':
            self.write(content)
        self.set_header('Content-Type', content_type)
        self.finish()

    def get_key(self, key, name):
        return 'hongniang:%s:%s' % (key, name)

handlers = [
    URLSpec('/', IndexHandler),
    URLSpec('/.*', ProxyHandler),
]

settings = dict(
    template_path = os.path.join(os.path.dirname(__file__), 'templates')
)

def main():
    define('debug', default=False, help='debug', type=bool)
    define('port', default=1900, help='port', type=int)

    define('rds_host', default='127.0.0.1', help='Redis host')
    define('rds_port', default=6379, help='Redis port', type=int)
    define('rds_db', default=0, help='Redis database', type=int)

    parse_command_line()
    settings['debug'] = options.debug

    application = Application(handlers, **settings)

    application.redis = redis.StrictRedis(host=options.rds_host, port=options.rds_port, db=options.rds_db)
    http_server = HTTPServer(application, xheaders=True)
    http_server.listen(options.port)
    logging.info('Listen on %d, debug=%s' % (options.port, options.debug))

    IOLoop.instance().start()

if __name__ == '__main__':
    main()
