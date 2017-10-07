#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# PYTHON_ARGCOMPLETE_OK
"""Crawl all configured sites and search for security issues."""

import argparse
import collections
import queue
import re
import shutil
import sys
import threading
from enum import Enum

import requests
import yaml
from termcolor import colored

try:
    import argcomplete
except ImportError:
    pass

TIMEOUT = 5  # seconds
THREAD_COUNT = 8

TASK_QUEUE = queue.Queue()
RESULTS = {}


DOMAIN_REGEX = re.compile(r'^http(s)?:\/\/(?P<domain>([\w\-\_]+\.)+[\w]+)(\/.*|$)')

class TASK_TYPES(Enum):
    END = 'END'  # stop worker
    GET = 'GET'  # get a simple site
    POST = 'POST'  # post data to a site
    HEAD = 'HEAD'  # send a head requests
    HOST = 'HOST'  # send fake host


class Task(collections.namedtuple('Task', ('task_type', 'url', 'args'))):
    __slots__ = ()
    def __new__(cls, task_type, url=None, args={}):
        return super(Task, cls).__new__(cls, task_type, url, args)

    @property
    def domain(self):
        """Return the domain part of url."""
        return DOMAIN_REGEX.match(self.url).groupdict()['domain']

    def __str__(self):
        """Translate task to a human readable string."""
        if self.task_type == TASK_TYPES.HOST:
            return 'GET {url} with host {host}'.format(url=self.url, host=self.args['host_name'])
        else:
            return '{method} {url}'.format(method=self.task_type.name, url=self.url)


def error(*msgs):
    """Print an error to stderr."""
    print(
        colored(
            ' '.join((str(x) for x in msgs)),
            'red',
        ),
        file=sys.stderr,
    )


def warning(*msgs):
    """Print a warning to stderr."""
    print(
        colored(
            ' '.join((str(x) for x in msgs)),
            'yellow',
        ),
        file=sys.stderr,
    )


def info(*msgs):
    """Print an info to stderr."""
    print(
        colored(
            ' '.join((str(x) for x in msgs)),
            'white',
        ),
        file=sys.stderr,
    )


def print_progress(verbosity):
    """Print current progress to stderr."""
    progress = 1 - TASK_QUEUE.qsize() / TASK_COUNT
    if verbosity == 0:
        # we can print a progress bar as nothing else spams to stderr
        col = shutil.get_terminal_size().columns
        col -= len('___%[ ]')
        bar_width = progress * col
        print('\r{prog: >3}%[{bar}{half}{white}]'.format(
            prog=int(progress * 100),
            bar=int(bar_width) * '=',
            half='-' if bar_width % 1 > .5 else ' ',
            white=' ' * (col - int(bar_width) - 1),
        ), end='', file=sys.stderr)
        if progress == 1:
            print()
    else:
        info('Progress: {prog: >3}%'.format(prog=int(progress * 100)))


def parse_args():
    """
    Parse cmd line args.

    Return an object containing the args and their values (see argparse doc).
    """
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        'config_file',
        type=argparse.FileType('r'),
        help='The yaml config file',
    )
    parser.add_argument(
        'out_file',
        type=argparse.FileType('w'),
        help='The yaml file to write the output',
    )
    parser.add_argument(
        '-v', '--verbose',
        action='count',
        default=0,
        help='More output',
    )
    parser.add_argument(
        '--no-progress',
        action='store_true',
        default=False,
        help='Hide progress output',
    )
    parser.add_argument(
        '--no-auto-save',
        action='store_true',
        default=False,
        help='Store results only at the end',
    )

    if 'argcomplete' in globals():
        argcomplete.autocomplete(parser)

    return parser.parse_args()


def http_get(url):
    """Try to get url. Return text or None in case of erros."""
    try:
        req = requests.get(url, timeout=TIMEOUT)
        req.raise_for_status()
        if not req.headers['content-type'].lower().startswith('text/html'):
            # ignore html files because most often this is not
            # what we are searching for
            return req.text
    except Exception:
        return None


def http_get_host(url, host):
    """Try to get url but send host. Return text on success."""
    try:
        req = requests.get(url, headers={'host': host}, timeout=TIMEOUT)
        req.raise_for_status()
        return req.text
    except Exception:
        return None


def crawl(task, verbosity=0):
    """Crawl task and search for security issues."""
    if verbosity > 2:
        info('Trying', str(task))

    if task.task_type == TASK_TYPES.GET:
        content = http_get(url=task.url)
        if content:
            if verbosity > 0:
                warning('Found', task.url)
            RESULTS[task.domain].append(str(task))
    elif task.task_type == TASK_TYPES.HOST:
        content = http_get_host(url=task.url, host=task.args['host_name'])
        if content:
            if verbosity > 0:
                warning('Found', task.url)
            RESULTS[task.domain].append(str(task))


def worker(verbosity=0, progress=True, auto_save_interval=0, out_file=None):
    """Execute jobs.

    progress: if True print progress to stderr.
    out_file: if given save current results periodically to this file
    """
    while True:
        task = TASK_QUEUE.get()
        if progress:
            print_progress(verbosity)
        if task.task_type == TASK_TYPES.END:
            return

        crawl(task, verbosity=verbosity)

        if out_file and TASK_QUEUE.qsize() % auto_save_interval == 0:
            if verbosity > 4:
                info('Saving...')
            save(out_file)  # save results every $auto_save_interval queries


def save(out_file):
    """Save the current state to out_file."""
    if not out_file.isatty():
        out_file.seek(0)
    yaml.dump(
        data=dict(RESULTS),
        stream=out_file,
        explicit_start=True,
    )
    if not out_file.isatty():
        out_file.truncate()


def main():
    """
    Run the script.

    Read config, create tasks for all sites using all search_for_files
    patterns, start threads, write out_file.
    """
    args = parse_args()
    config = yaml.load(stream=args.config_file)

    for site in set(config['sites']):
        # ensure we don't check a site twice
        # sets also scramble entries. It's ok if the sites will be scrambled,
        # because so one slow site does not slow down all threads simultaniously
        # and maybe we can trick DOS prevention mechanisms.
        domain = DOMAIN_REGEX.match(site).groupdict()['domain']
        RESULTS[domain] = []  # empty list for each domain to store the results
        if not site.endswith('/'):
            site += '/'

        for file_name in set(config.get('search_for_files', [])):
            # ensure we don't check a file twice
            TASK_QUEUE.put(
                Task(
                    task_type=TASK_TYPES.GET,
                    url=site + file_name.format(domain=domain),
                )
            )
        for host_name in set(config.get('fake_host_names', [])):
            # ensure we don't check a host twice
            TASK_QUEUE.put(
                Task(
                    task_type=TASK_TYPES.HOST,
                    url=site,
                    args={'host_name': host_name.format(domain=domain)},
                )
            )

    global TASK_COUNT
    TASK_COUNT = TASK_QUEUE.qsize()

    threads = []
    for _ in range(THREAD_COUNT):
        thread = threading.Thread(
            target=worker,
            daemon=True,
            kwargs={
                'verbosity': args.verbose,
                'progress': not args.no_progress,
                'auto_save_interval': 100,
                'out_file': None if args.no_auto_save or args.out_file.isatty() else args.out_file,
            }
        )
        threads.append(thread)
        thread.start()
        TASK_QUEUE.put(Task(
            task_type=TASK_TYPES.END  # add one END task per thread at end of queue
        ))

    for thread in threads:
        thread.join()

    if not TASK_QUEUE.empty():
        error('[x] Exiting due to exception in thread')
        exit(1)

    save(args.out_file)


if __name__ == '__main__':
    main()
