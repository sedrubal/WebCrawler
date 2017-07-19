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
RESULTS = collections.defaultdict(list)


DOMAIN_REGEX = re.compile(r'^http(s)?:\/\/(?P<domain>([\w\-\_]+\.)+[\w]+)(\/.*|$)')


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


def crawl(url, verbosity=0):
    """Crawl url and search for security issues."""
    domain = DOMAIN_REGEX.match(url).groupdict()['domain']
    if verbosity > 2:
        info('Trying', url)
    content = http_get(url)
    if content:
        if verbosity > 0:
            warning('Found', url)

        RESULTS[domain].append(url)


def worker(verbosity=0, progress=True, out_file=None):
    """Execute jobs.

    progress: if True print progress to stderr.
    out_file: if given save current results periodically to this file
    """
    while True:
        site = TASK_QUEUE.get()
        if progress:
            print_progress(verbosity)
        if out_file and TASK_QUEUE.qsize() % 100 == 0:
            save(out_file)  # save results every 100 queries
        if not site:
            return

        crawl(site, verbosity=verbosity)


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
    sites = set()  # ensure we don't check a site twice
    # sets also scramble entries. It's ok if the sites will be scrambled,
    # because so one slow site does not slow down all threads simultaniously
    # and maybe we can trick DOS prevention mechanisms.

    for site in config['sites']:
        for file_name in config['search_for_files']:
            domain = DOMAIN_REGEX.match(site).groupdict()['domain']
            if not site.endswith('/'):
                site += '/'
            sites.add(site + file_name.format(domain=domain))

    global TASK_COUNT
    TASK_COUNT = len(sites)
    [TASK_QUEUE.put(site) for site in sites]  # add all sites to queue

    threads = []
    for _ in range(THREAD_COUNT):
        thread = threading.Thread(
            target=worker,
            daemon=True,
            kwargs={
                'verbosity': args.verbose,
                'progress': not args.no_progress,
                'out_file': None if args.no_auto_save or args.out_file.isatty() else args.out_file,
            }
        )
        threads.append(thread)
        thread.start()
        TASK_QUEUE.put(None)  # add one None per thread at end of queue

    for thread in threads:
        thread.join()

    if not TASK_QUEUE.empty():
        error('[x] Exiting due to exception in thread')
        exit(1)

    save(args.out_file)


if __name__ == '__main__':
    main()
