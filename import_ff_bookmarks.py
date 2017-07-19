#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# PYTHON_ARGCOMPLETE_OK
"""Convert a firefox bookmarks export json file to a yaml list you can use for webcrawler."""

import argparse
import yaml
from webcrawler import DOMAIN_REGEX

try:
    import argcomplete
except ImportError:
    pass


def extract_urls(bm_node):
    """Traverse ff bookmarks tree and return list of all urls."""
    urls = set()
    if 'uri' in bm_node and DOMAIN_REGEX.match(bm_node['uri']):
        url = bm_node['uri']
        urls.add(
            url[
                :min([
                    i for i in (
                        url.find('?'), url[9:].find('/'), url.find('#')
                    )
                    if i != -1
                ] or [-1])
            ] + '/'  # strip all GET params (?) and anchors (#) and ensure URLs end with /
        )
    elif 'children' in bm_node:
        for child in bm_node['children']:
            urls = urls.union(extract_urls(child))
    return urls


def parse_args():
    """
    Parse cmd line args.

    Return an object containing the args and their values (see argparse doc).
    """
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        'bookmarks_file',
        type=argparse.FileType('r'),
        help='The firefox bookmarks export json file',
    )
    parser.add_argument(
        'out_file',
        type=argparse.FileType('w'),
        help='The yaml file to write the output',
    )

    if 'argcomplete' in globals():
        argcomplete.autocomplete(parser)

    return parser.parse_args()


def main():
    """Open file, read all bookmarks and dump them as yaml to stdout."""
    args = parse_args()

    bookmarks_tree = yaml.load(stream=args.bookmarks_file)
    yaml.dump(
        data={'sites': list(sorted(extract_urls(bookmarks_tree)))},
        stream=args.out_file,
        explicit_start=True,
        default_flow_style=False,
    )


if __name__ == '__main__':
    main()
