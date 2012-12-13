#!/usr/bin/python
# coding=utf-8

import os

pid_file = os.path.join(os.path.split(__file__)[0], 'server.pid')
log_file = os.path.join(os.path.split(__file__)[0], 'server.log')
cfg_file = os.path.join(os.path.split(__file__)[0], 'mongo-orchestration.config')

import logging
logging.basicConfig(level=logging.DEBUG, filename=log_file, filemode='w')
logger = logging.getLogger(__name__)

import argparse
import json
import sys

from bottle import run, default_app

# from lib.rs import RS
from lib import set_storage, cleanup_storage

default_app.push()
import apps.hosts
import apps.rs
import apps.sh
app = default_app.pop()

import StringIO
import atexit
DEFAULT_PORT = 8889


class Daemon(object):

    def __init__(self, no_fork=False):
        self.pid_path = pid_file
        self.no_fork = no_fork

    def start(self):
        if os.path.exists(self.pid_path):
            print "server.py has already started"
            return
        if not self.no_fork:
            try:
                pid = os.fork()
                if pid > 0:
                    # exit first parent
                    sys.exit(0)
            except OSError, e:
                sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
                sys.exit(1)

            # do second fork
            try:
                pid = os.fork()
                if pid > 0:
                    # exit from second parent
                    sys.exit(0)
            except OSError, e:
                sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
                sys.exit(1)
            sys.stdout = StringIO.StringIO()
            sys.stderr = sys.stdout
            open(self.pid_path, 'w').write(str(os.getpid()))

    def stop(self, exit=True):
        cleanup_storage()
        if os.path.exists(self.pid_path):
            try:
                pid = int(open(self.pid_path).read())
                os.kill(pid, 15)
            except (OSError):
                pass
            os.remove(self.pid_path)
        if exit:
                sys.exit(0)

    def restart(self):
        self.stop(exit=False)
        self.start()


def read_env():
    logging.debug("read_env()")
    parser = argparse.ArgumentParser(description='mongo-orchestration server')
    parser.add_argument('-f', '--config', action='store', default=cfg_file, type=str, dest='config')
    parser.add_argument('-e', '--env', action='store', type=str, dest='env', default='default')
    parser.add_argument(action='store', type=str, dest='command', default='start', choices=('start', 'stop', 'restart'))
    parser.add_argument('--no-fork', action='store_true', dest='no_fork', default=False)
    parser.add_argument('-p', '--port', action='store', dest='port', default=DEFAULT_PORT)
    args = parser.parse_args()

    if args.command == 'stop':
        return args
    try:
        config = json.loads(open(args.config, 'r').read())
        args.release_path = config['releases'][args.env]
        return args
    except (IOError):
        print "config file not found"
        sys.exit(1)
    except (ValueError):
        print "config file is corrupted"
        sys.exit(1)


def setup(release_path):
    logger.debug("setup({release_path})".format(**locals()))
    db = os.path.join(os.path.split(__file__)[0], 'mongo-pids')
    logger.debug("db path: {db}".format(**locals()))
    set_storage(db, release_path)
    logger.debug("rs.set_settings done")
    atexit.register(cleanup_storage)


def delete_pid():
    logger.debug("delete_pid()")
    if args.no_fork and os.path.exists(pid_file):
        logger.debug("remove pid file {pid_file}".format(pid_file=pid_file))
        os.remove(pid_file)

args = read_env()
if args.command != 'stop':
    setup(args.release_path)
else:
    setup('')
atexit.register(delete_pid)
getattr(Daemon(args.no_fork), args.command)()
run(app, host='localhost', port=args.port, debug=False, reloader=False)
