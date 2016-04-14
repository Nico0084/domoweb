#!/usr/bin/env python

import sys
if sys.version_info < (2, 6):
    print "Sorry, requires Python 2.6 or 2.7."
    sys.exit(1)

# MQ
import os
from zmq.eventloop import ioloop
ioloop.install()
import domoweb
from domoweb.handlers import MainHandler, ConfigurationHandler, WSHandler, NoCacheStaticFileHandler, MQHandler, UploadHandler,MultiStaticFileHandler, LoginHandler
from domoweb.loaders import packLoader, mqDataLoader

from domoweb import ui_methods

#import tornado.ioloop
import tornado.web
import tornado.httpserver
from tornado.options import options
import logging

logging.basicConfig(format='%(asctime)s %(name)s:%(levelname)s %(message)s',level=logging.INFO)

logger = logging.getLogger('domoweb')

domoweb.FULLPATH = os.path.normpath(os.path.abspath(__file__))
domoweb.PROJECTPATH = os.path.dirname(domoweb.FULLPATH)
domoweb.PACKSPATH = os.path.join(domoweb.PROJECTPATH, 'packs')
domoweb.VARPATH = "/var/lib/domoweb/"

application = tornado.web.Application(
    handlers=[
        (r"/(\d*)", MainHandler),
        (r"/configuration", ConfigurationHandler),
        (r"/widget/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(os.path.dirname(__file__), "packs", 'widgets')}),
        (r"/theme/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(os.path.dirname(__file__), "packs", 'themes')}),
        (r"/images/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(os.path.dirname(__file__), "static", 'images')}),
        (r"/libraries/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(os.path.dirname(__file__), "static", 'libraries')}),
        (r"/css/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(os.path.dirname(__file__), "static", 'css')}),
        (r"/js/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(os.path.dirname(__file__), "static", 'js')}),
        (r"/locales/domoweb/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(os.path.dirname(__file__), "static", "locales")}),
        (r"/locales/(.*)/(.*)/(.*)", MultiStaticFileHandler, { "path": os.path.join(os.path.dirname(__file__), "packs", 'widgets')}),
        (r"/components/(.*)", NoCacheStaticFileHandler, {"path": os.path.join(os.path.dirname(__file__), "components")}),
        (r"/manifests/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(os.path.dirname(__file__), "manifests")}),
        (r'/ws/', WSHandler),
        (r'/upload', UploadHandler),
        (r"/backgrounds/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(domoweb.VARPATH, "backgrounds")}),
        (r"/login", LoginHandler),
        (r"/(.*)", MainHandler),
    ],
    template_path=os.path.join(os.path.dirname(__file__), "templates"),
    debug=True,
    autoreload=True,
    ui_methods=ui_methods,
    cookie_secret="DomowebAndDomogikAreReallyAwesomeProjects",
    login_url="/login"
)

if __name__ == '__main__':

#    domoweb.VERSION = "dev.%s" % commands.getoutput("cd %s ; hg id -n 2>/dev/null" % domoweb.PROJECTPATH)

    # Check log folder
    if not os.path.isdir("/var/log/domoweb"):
        sys.stderr.write("Error: /var/log/domoweb do not exist")
        sys.exit(1)

    # Check config file
    SERVER_CONFIG = '/etc/domoweb.cfg'
    if not os.path.isfile(SERVER_CONFIG):
        sys.stderr.write("Error: Can't find the file '%s'\n" % SERVER_CONFIG)
        sys.exit(1)

    options.define("sqlite_db", default="/var/lib/domoweb/db.sqlite", help="Database file path", type=str)
    options.define("port", default=40404, help="Launch on the given port", type=int)
    options.define("debug", default=False, help="Debug mode", type=bool)
    options.define("rest_url", default="http://127.0.0.1:40406/rest", help="RINOR REST Url", type=str)
    options.define("develop", default=False, help="Develop mode", type=bool)
    options.define("use_ssl", default=False, help="Use SSL", type=bool)
    options.define("ssl_certificate", default="ssl_cert.pem", help="SSL certificate file path", type=str)
    options.define("ssl_key", default="ssl_key.pem", help="SSL key file path", type=str)
    options.parse_config_file(SERVER_CONFIG)

    logger.info("Running from : %s" % domoweb.PROJECTPATH)

    packLoader.loadWidgets(domoweb.PACKSPATH, options.develop)
    packLoader.loadThemes(domoweb.PACKSPATH, options.develop)
    if not os.path.isdir(os.path.join(domoweb.VARPATH, 'backgrounds')):
        os.mkdir(os.path.join(domoweb.VARPATH, 'backgrounds'))
        logger.info("Creating : %s" % os.path.join(domoweb.VARPATH, 'backgrounds'))
    if not os.path.isdir(os.path.join(domoweb.VARPATH, 'backgrounds', 'thumbnails')):
        os.mkdir(os.path.join(domoweb.VARPATH, 'backgrounds', 'thumbnails'))

    mqDataLoader.loadDatatypes(options.develop)
    mqDataLoader.loadDevices(options.develop)

    logger.info("Starting tornado web server")
    if options.use_ssl:
        logger.info("SSL activated")
        logger.info("SSL certificate file : {0}".format(options.ssl_certificate))
        logger.info("SSL certificate file : {0}".format(options.ssl_key))
        http_server = tornado.httpserver.HTTPServer(application,
                                            ssl_options = {
                                                "certfile": os.path.join(options.ssl_certificate),
                                                "keyfile": os.path.join(options.ssl_key)
                                            })
    else:
        logger.info("SSL not activated")
        http_server = tornado.httpserver.HTTPServer(application)
                                                
    http_server.listen(options.port)
    logger.info("Starting MQ Handler")
    MQHandler()
    ioloop.IOLoop.instance().start() 
