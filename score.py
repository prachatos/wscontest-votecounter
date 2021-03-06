#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
score.py
A script to count proofread and validated pages for the Wikisource anniversary
contest.
This script is part of wscontest-votecounter.
(<https://github.com/CristianCantoro/wscontest-votecounter>)
---
usage: score.py [-h] [--booklist-cache BOOKLIST_CACHE] [--cache CACHE_FILE]
                [--config CONFIG_FILE] [-d] [--enable-cache] [-f BOOKS_FILE]
                [-o OUTPUT_TSV] [-v]
Count proofread and validated pages for the Wikisource contest.
optional arguments:
  -h, --help            show this help message and exit
  --booklist-cache BOOKLIST_CACHE
                        JSON file to read and store the booklist cache
                        (default: {BOOKS_FILE}.booklist_cache.json)
  --cache CACHE_FILE    JSON file to read and store the cache (default:
                        {BOOKS_FILE}.cache.json)
  --config CONFIG_FILE  INI file to read configs (default: contest.conf.ini)
  -d                    Enable debug output (implies -v)
  --enable-cache        Enable caching
  -f BOOKS_FILE         TSV file with the books to be processed (default:
                        books.tsv)
  -o OUTPUT_TSV         Output file (default: {BOOKS_FILE}.results.tsv)
  -v                    Enable verbose output
---
The MIT License (MIT)
Original script:
Copyright (c) 2013 Joan Creus <joan.creus.c@gmail.com>
Modified script:
Copyright (c) 2015 Ricordisamoa
wscontest-votecounter:
Copyright (c) 2015 CristianCantoro <kikkocristian@gmail.com>
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""
import re
import csv
import codecs
import logging
import argparse
import configparser
from collections import defaultdict
from collections import Counter
from functools import reduce
from operator import add
from datetime import datetime
import urllib.parse
import urllib.request

# Try to use yajl, a faster module for JSON
# import json
try:
    import yajl as json
except ImportError:
    import json

### GLOBALS AND DEFAULTS ###
# Files
BOOKS_FILE = "books.tsv"
CACHE_FILE = "{BOOKS_FILE}.cache.json"
BOOKLIST_CACHE_FILE = "{BOOKS_FILE}.booklist_cache.json"
CONFIG_FILE = "contest.conf.ini"
OUTPUT_TSV = '{BOOKS_FILE}.results.tsv'

# URLs
WIKISOURCE_API = 'https://{lang}.wikisource.org/w/api.php'
COMMONS_API = 'https://commons.wikimedia.org/w/api.php'
### ###

### logging ###
LOGFORMAT_STDOUT = {logging.DEBUG: '%(funcName)s:%(lineno)s - '
                                   '%(levelname)-8s: %(message)s',
                    logging.INFO: '%(levelname)-8s: %(message)s',
                    logging.WARNING: '%(levelname)-8s: %(message)s',
                    logging.ERROR: '%(levelname)-8s: %(message)s',
                    logging.CRITICAL: '%(levelname)-8s: %(message)s'
                    }

# root logger
rootlogger = logging.getLogger()
lvl_logger = logging.DEBUG
rootlogger.setLevel(lvl_logger)

console = logging.StreamHandler()
console.setLevel(lvl_logger)

formatter = logging.Formatter(LOGFORMAT_STDOUT[lvl_logger])
console.setFormatter(formatter)

rootlogger.addHandler(console)

logger = logging.getLogger('score')
logger.setLevel(lvl_logger)
###


def read_cache(cache_file):
    logger.debug("Reading cache: {}".format(cache_file))
    try:
        with codecs.open(cache_file, 'r', 'utf-8') as f:
            cache = json.load(f)

    # If the file is not found  Python 3.4 will raise FileNotFoundError which is
    # a subclass of IOError.
    # See also:
    # http://sebastianraschka.com/Articles/python3_OSError.html
    except IOError:
        cache = dict()

    return cache

def convBeng(num):
	bn = ['০', '১', '২', '৩', '৪', '৫', '৬', '৭', '৮', '৯']
	ans = ''
	if int(num) < 10: return bn[int(num)]
	while int(num) > 0:
		ans = bn[int(num) % 10] + ans
		num = str(int(int(num) / 10))
	return ans

def write_cache(cache, cache_file):
    logger.debug("Writing cache: {}".format(cache_file))
    with codecs.open(cache_file, 'w', 'utf-8') as f:
        json.dump(cache, f)


def get_numpages(book, api):

    params = {
        'action': 'query',
        'format': 'json',
        'prop': 'imageinfo',
        'titles': 'File:{book}'.format(book=book),
        'iilimit': '50',
        'iiprop': 'size'
    }

    params = urllib.parse.urlencode(params).encode('ascii')
    logger.info("\tRequest image info for file 'File:{book}'".format(book=book))

    with urllib.request.urlopen(api, params) as f:
        data = json.loads(f.read().decode('utf-8'))
        try:
            numpages = list(data['query']['pages'].values())[0]['imageinfo'][0]['pagecount']
        except KeyError: numpages = 0

        return int(numpages)


def get_books(books_file, booklist_cache):

    booklist = 'CACHE_BOOKS_LIST'
    cache = read_cache(booklist_cache)

    if booklist not in cache:
        cache[booklist] = dict()

    with codecs.open(books_file, 'r', 'utf-8') as f:
        lines = f.readlines()
        clean_lines = [line.strip().strip('\"') for line in lines
                       if line.strip() and (not line.startswith("#"))]

    for book in clean_lines:
        if book not in cache[booklist]:
            end = get_numpages(book, COMMONS_API)
            #if end == 0:
            #	end = get_numpages(book, WIKISOURCE_API)
            cache[booklist][book] = end

            write_cache(cache, booklist_cache)

    return [(book, end) for book, end in cache[booklist].items()]


def get_page_revisions(book, page, lang, enable_cache, cache_file):

    cache = None
    if enable_cache:
        cache = read_cache(cache_file)

    page = str(page)
    # Request is cached
    if enable_cache and (book in cache) and (page in cache[book]):
        logger.info("Request is cached...")
        return cache[book][page]

    # Request is NOT cached
    if enable_cache and book not in cache:
        cache[book] = dict()

    params = {
        'action': 'query',
        'format': 'json',
        'prop': 'revisions',
        'titles': 'Page:{book}/{page}'.format(book=book, page=convBeng(page)),
        'rvlimit': '50',
        'rvprop': 'user|timestamp|content'
    }
    params = urllib.parse.urlencode(params).encode('ascii')
    logger.info("\tRequest page 'Page:{book}/{page}'".format(book=book, page=convBeng(page)))
    with urllib.request.urlopen(WIKISOURCE_API.format(lang=lang),
                                params) as f:

        data = json.loads(f.read().decode('utf-8'))
        if enable_cache:
            cache[book][page] = data
            write_cache(cache, cache_file)
            return cache[book][page]
        else:
            return data


def get_score(books_file,
              contest_start,
              contest_end,
              lang,
              booklist_cache,
              enable_cache,
              cache_file):
    # defaults are 0
    books = get_books(books_file, booklist_cache)
    tot_punts = dict()
    tot_vali = dict()
    tot_revi = dict()
    tot_notext = dict()
    tot_prob = dict()
    
    for i, (book, end) in enumerate(books):
        logger.info("Processing book... \"{}\"".format(book))

        punts = defaultdict(int)
        vali = defaultdict(int)
        revi = defaultdict(int)
        notext = defaultdict(int)
        prob = defaultdict(int)
		
        logger.info("Querying the API...")
        for pag in range(1, end + 1):
            query = get_page_revisions(book,
                                       pag,
                                       lang,
                                       enable_cache,
                                       cache_file)
            try:
                revs = list(query['query']['pages'].values())[0]['revisions'][::-1]
            except KeyError:
                continue
            old = None
            oldUser = None
            oldTimestamp = None
            for rev in revs:
                timestamp = datetime.strptime(rev['timestamp'], '%Y-%m-%dT%H:%M:%SZ')
                user = rev['user']
                txt = rev['*']
                quality_level, newUser = re.findall('<pagequality level="(\d)" user="(.*?)" />', txt)[0]
                quality_level = int(quality_level)
                newUser = user
                if quality_level == 0 and (old is None) and timestamp >= contest_start and timestamp < contest_end:
                    logger.debug("User: {} - Case 0 - No text".format(newUser))
                    # User b proofreads the page pag
                    punts[newUser] += 0.5
                    notext[newUser] += 1
                    
                if quality_level == 2 and (old is None or old < 2) and timestamp >= contest_start and timestamp < contest_end:
                    logger.debug("User: {} - Case 1 - Problematic page".format(newUser))
                    # User b proofreads the page pag
                    punts[newUser] += 0.5
                    prob[newUser] += 1
                # if old is None: Page doesn't exist before
                if quality_level == 3 and (old is None or old < 3) and timestamp >= contest_start and timestamp < contest_end:
                    logger.debug("User: {} - Case 2 - Proofread the page".format(newUser))
                    # User b proofreads the page pag
                    punts[newUser] += 3
                    revi[newUser] += 1

                if quality_level == 4 and old == 3 and timestamp >= contest_start and timestamp < contest_end:
                    logger.debug("User: {} - Case 3 - Validation".format(newUser))
                    # User b validates page pag
                    punts[newUser] += 1
                    vali[newUser] += 1

                #if quality_level == 3 and old == 4 and timestamp >= contest_start:
                #    if oldTimestamp >= contest_start and oldTimestamp <= contest_end:
                #        logger.debug("User: {} - Case 3 - Reverted validation".format(newUser))
                #        punts[oldUser] -= 1
                #        vali[oldUser] -= 1

                #if quality_level < 3 and old == 3 and timestamp >= contest_start:
                #    if oldTimestamp >= contest_start and oldTimestamp <= contest_end:
                #        logger.debug("User: {} - Case 4 - Reverted proofread".format(newUser))
                #        punts[oldUser] -= 3
                #        revi[oldUser] -= 1

                old = quality_level
                oldUser = newUser
                oldTimestamp = timestamp

            logger.debug(punts)
            logger.debug(vali)
            logger.debug(revi)


        tot_punts = reduce(add, (Counter(punts), Counter(tot_punts)))
        tot_vali = reduce(add, (Counter(vali), Counter(tot_vali)))
        tot_revi = reduce(add, (Counter(revi), Counter(tot_revi)))
        tot_notext = reduce(add, (Counter(notext), Counter(tot_notext)))
        tot_prob = reduce(add, (Counter(prob), Counter(tot_prob)))
		
        logger.debug(tot_punts)
        logger.debug(tot_vali)
        logger.debug(tot_revi)
        logger.debug(tot_notext)
        logger.debug(tot_prob)

    return tot_punts, tot_vali, tot_revi, tot_prob, tot_notext


def get_rows(punts, vali, revi, prob, notext):
    # sorting:
    # results are ordered by:
    # (punts desc, revi desc, vali desc, username asc)
    # to obtain this first first sort by username ascending, then by
    # (punts, revi, vali) descending
    return [(user, punts[user], vali[user], revi[user], prob[user], notext[user])
            for user in sorted(sorted(punts.keys()),
                               key=lambda u: (punts[u], revi[u], vali[u], prob[u], notext[u]),
                               reverse=True)]


def write_csv(rows, output):
    csv_fields = ['user', 'punts', 'vali', 'revi', 'prob', 'notext']
    with open(output, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile,
                                fieldnames=csv_fields,
                                delimiter='\t',
                                quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()

        for row in rows:
            writer.writerow(dict(zip(csv_fields, row)))


def read_config(config_file):
    config = {}
    parser = configparser.ConfigParser()
    parser.read(config_file)

    config['contest'] = dict([(k ,v) for k, v in parser['contest'].items()])
    return config


def main(config):
    books_file = config['books_file']
    contest_start = datetime.strptime(config['contest']['start_date'], "%Y-%m-%d %H:%M:%S")
    contest_end = datetime.strptime(config['contest']['end_date'], "%Y-%m-%d %H:%M:%S")
    lang = config['contest']['language']
    booklist_cache = config['booklist_cache']
    cache_file = config['cache_file']
    enable_cache = config['enable_cache']
    output = config['output']

    scores = get_score(books_file,
                       contest_start,
                       contest_end,
                       lang,
                       booklist_cache,
                       enable_cache,
                       cache_file
                       )

    rows = get_rows(*scores)

    write_csv(rows, output)


if __name__ == '__main__':

    DESCRIPTION = 'Count proofread and validated pages for the Wikisource contest.'
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument('--booklist-cache', default=BOOKLIST_CACHE_FILE, metavar='BOOKLIST_CACHE',
                        help='JSON file to read and store the booklist cache (default: {})'.format(BOOKLIST_CACHE_FILE))
    parser.add_argument('--cache', default=CACHE_FILE, metavar='CACHE_FILE',
                        help='JSON file to read and store the cache (default: {})'.format(CACHE_FILE))
    parser.add_argument('--config', default=CONFIG_FILE, metavar='CONFIG_FILE',
                        help='INI file to read configs (default: {})'.format(CONFIG_FILE))
    parser.add_argument('-d', action='store_true',
                        help='Enable debug output (implies -v)')
    parser.add_argument('--enable-cache', action='store_true',
                        help='Enable caching')
    parser.add_argument('-f', default=BOOKS_FILE, metavar='BOOKS_FILE',
                        help='TSV file with the books to be processed (default: {})'.format(BOOKS_FILE))
    parser.add_argument('-o', default=OUTPUT_TSV, metavar='OUTPUT_TSV',
                        help='Output file (default: {})'.format(OUTPUT_TSV))
    parser.add_argument('-v', action='store_true',
                        help='Enable verbose output')

    args = parser.parse_args()

    config_file = args.config
    config = read_config(config_file)

    config['books_file'] = args.f

    # Booklist file
    if "BOOKS_FILE" in args.booklist_cache:
        config['booklist_cache'] = args.booklist_cache.format(
            BOOKS_FILE=config['books_file'])
    else:
        config['booklist_cache'] = args.booklist_cache

    # Cache file
    config['enable_cache'] = args.enable_cache
    if "BOOKS_FILE" in args.cache:
        config['cache_file'] = args.cache.format(
            BOOKS_FILE=config['books_file'])
    else:
        config['cache_file'] = args.cache

    # TSV output
    if "BOOKS_FILE" in args.o:
        config['output'] = args.o.format(
            BOOKS_FILE=config['books_file'])
    else:
        config['output'] = args.o

    # Verbosity/Debug
    config['verbose'] = args.v or args.d
    config['debug'] = args.d

    lvl_config_logger = logging.WARNING
    if config['verbose']:
        lvl_config_logger = logging.INFO

    if config['debug']:
        lvl_config_logger = logging.DEBUG

    formatter = logging.Formatter(LOGFORMAT_STDOUT[lvl_config_logger])
    console.setFormatter(formatter)
    rootlogger.setLevel(lvl_config_logger)
    logger.setLevel(lvl_config_logger)

    logger.info("Enable verbose output")
    logger.debug("Enable debug")
    logger.debug(args)
    logger.debug(config)

    main(config)

logger.info("All done!")
