import os
import logging

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

http_client = AsyncHTTPClient()

class IndexHandler(RequestHandler):
    def get(self):
        self.render('index.html')

class ProxyHandler(RequestHandler):
    @asynchronous
    @gen.engine
    def get(self):
        maps = {
            'fonts.twinsant.com': 'fonts.googleapis.com',
            'themes.twinsant.com': 'themes.googleusercontent.com',
        }
        url = 'http://%s%s' % (maps[self.request.host], self.request.uri)
        logging.debug('Fetching %s ...' % url)
        response = yield gen.Task(http_client.fetch, url, connect_timeout=60.0, request_timeout=60.0)
        if response.code == 200:
            content_type = response.headers.get('Content-Type')
            if self.request.host == 'fonts.twinsant.com':
                html = response.body.replace('http://themes.googleusercontent.com', 'http://themes.twinsant.com')
                self.write(html)
            if self.request.host == 'themes.twinsant.com':
                self.write(response.body)
            self.set_header('Content-Type', content_type)
        else:
            raise HTTPError(response.code)
        self.finish()

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

    parse_command_line()
    settings['debug'] = options.debug

    application = Application(handlers, **settings)
    http_server = HTTPServer(application, xheaders=True)
    http_server.listen(options.port)
    logging.info('Listen on %d, debug=%s' % (options.port, options.debug))

    IOLoop.instance().start()

if __name__ == '__main__':
    main()
