#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crawl all configured sites for security issues."""

import argparse
import queue
import re
import sys
import threading
import collections

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


DOMAIN_REGEX = re.compile(r'^http(s)?:\/\/(?P<domain>([\w\-\_]+\.)+[\w]+)\/.*')


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

    if 'argcomplete' in globals():
        argcomplete.autocomplete(parser)

    return parser.parse_args()


def http_get(url):
    """Try to get url. Return text or None in case of erros."""
    try:
        req = requests.get(url)
        req.raise_for_status()
        return req.text
    except requests.exceptions.HTTPError:
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


def worker(verbosity=0):
    """Execute jobs."""
    while True:
        site = TASK_QUEUE.get()
        if not site:
            return

        crawl(site, verbosity=verbosity)


def main():
    """
    Run the script.

    Read config, create tasks for all sites using all search_for_files
    patterns, start threads, write out_file.
    """
    args = parse_args()
    config = yaml.load(stream=args.config_file)

    for site in config['sites']:
        for file_name in config['search_for_files']:
            domain = DOMAIN_REGEX.match(site).groupdict()['domain']
            TASK_QUEUE.put(site + file_name.format(domain=domain))

    threads = []
    for _ in range(THREAD_COUNT):
        thread = threading.Thread(
            target=worker,
            daemon=True,
            kwargs={'verbosity': args.verbose}
        )
        threads.append(thread)
        thread.start()
        TASK_QUEUE.put(None)  # add one None per thread at end of queue

    for thread in threads:
        thread.join()

    if not TASK_QUEUE.empty():
        error('[x] Exiting due to exception in thread')
        exit(1)

    # write results
    yaml.dump(data=dict(RESULTS), stream=args.out_file)


if __name__ == '__main__':
    main()
