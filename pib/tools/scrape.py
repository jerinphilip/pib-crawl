from urllib.request import Request, urlopen
from bs4 import BeautifulSoup
import time
import numpy as np
import logging
from argparse import ArgumentParser
from datetime import datetime
import langid
import re
from .lmdbcache import LMDBCacheAPI
from .. import db
from ..models import Entry

class CrawlState:
    def __init__(self, path):
        self.path = path
        self.cache_types = ['success', 'error', 'empty']
        self.cache = {}

        for cache_type in self.cache_types:
            path = '{}.{}'.format(self.path, cache_type)
            self.cache[cache_type] = LMDBCacheAPI(path)

    def is_done(self, key):
        flags = [self.cache[_type].findkey(key) for _type in self.cache_types]
        return any(flags)

    def write(self, cache_type, key, content):
        assert cache_type in self.cache_types, \
                'cache_type has to be in {}'.format(self.cache_types)
        self.cache[cache_type].write(key, content)

    def get(self, key):
        if not self.is_done(key):
            return (False, None)

        record = self.cache['success'][key] 
        return (True, record)

class CachedCrawler:
    headers = {
       'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36',
       'referrer': 'https://google.com',
       'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3',
       'Accept-Encoding': 'gzip, deflate, br',
       'Accept-Language': 'en-US,en;q=0.9',
    }

    def __init__(self, path):
        self.state = CrawlState(path)

    def retrieve_pib_article(self, key):
        try:
            soup = self.construct_soup('https://pib.gov.in/PressReleasePage.aspx?PRID={}'.format(key))
            content = soup.find('div', {'id': 'PdfDiv'})
            other = soup.find('div', {'class': 'ReleaseLang'})
            links = other.find_all('a', href=True)
            print(links)
            text = content.text.strip()
            if (text != "Posted On:"):
                self.state.write('success', key, text)
                print('PIB({}) properly parsed'.format(key))
            else:
                self.state.write('empty', key, True)
                print('PIB({}) found empty'.format(key))
            return text

        except Exception as e:
            print(e)
            self.state.write('error', key, True)
            print('PIB({}) error.'.format(key))

        return None

    def construct_soup(self, url):
        request = Request(url, headers=self.headers)
        web_byte = urlopen(request).read()
        web_page = web_byte.decode('utf-8')
        soup = BeautifulSoup(web_page, 'html.parser')
        return soup

    def cached_load(self, key):
        present, record = self.state.get(key) 
        if record is not None:
            return record
        return self.retrieve_pib_article(state, key)

class PIBArticle:
    def __init__(self, lang, ministry, place, title, content, links):
        self.ministry = ministry
        self.lang = lang
        self.place = place
        self.title = title
        self.content = content
        self.links = []
        self.validate()

    @classmethod
    def fromCrawl(cls, _dict):
        pass

class DataParser:
    @staticmethod
    def filter(text):
        flag=1
        garbage = ['Posted On:','by PIB','ID:','/']
        for fil in garbage:
            if fil in text:
                flag=0
        return flag

    @staticmethod
    def parse(text):

        lang, *_ = langid.classify(text)
        lines = text.strip().split('\n')

        output = []

        day, month, year, time, place, date = [None]*6

        for line in lines:
            line = line.strip()
            if line and DataParser.filter(line):
                output.append(line)

            pattern = re.compile('([0-9]+) ([A-Z]+) ([0-9]+) ([0-9]+:[0-9]+[AP]M) by PIB (.+)')
            matches = pattern.match(line)
            if matches:
                day, month, year, time, place = matches.groups()
                date_string = f'{month} {day} {year} {time}'
                date = datetime.strptime(date_string, '%b %d %Y %I:%M%p')

        content = '\n'.join(output)

        return { 
            "lang": lang, "content": content,
            "date": date, "city": place
        }

def add_entry(key, text, update_if_exists=False):
    processed =  DataParser.parse(text)
    processed['id'] = key
    entry = Entry.query.get(key)
    if entry is None:
        entry = Entry(**processed)
        print(f"{key} does not exists in db; adding")
        db.session.add(entry)
        # db.session.commit()
    elif update_if_exists:
        print(f"{key} exists in db; updating")
        for tag in processed:
            setattr(entry, tag, processed[tag])
        db.session.add(entry)

def main(args):
    crawler = CachedCrawler(args.path)
    for idx in range(args.begin, args.end):
        key = str(idx)
        text = None

        if args.force_redo: 
            text = crawler.retrieve_pib_article(key)

        elif args.load_from_cache:
            text = crawler.cached_load(key)

        update_if_exists = args.force_redo or args.load_from_cache
        if text is not None:
            add_entry(key, text, update_if_exists)

        if idx%args.commit_interval == 0:
            db.session.commit()
            db.session.flush()

    db.session.commit()
    db.session.flush()

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--path', help='path to lmdb save location', type=str, required=True)
    parser.add_argument('--begin', help='Begin PIB ID', type=int, required=True)
    parser.add_argument('--end', help='End PIB ID', type=int, required=True)
    parser.add_argument('--force-redo', help='Ignore if already exists anywhere', action='store_true')
    parser.add_argument('--load-from-cache', help='Ignore if already exists anywhere', action='store_true')
    parser.add_argument('--commit-interval', help='Transaction commit interval', type=int, default=10000)
    args = parser.parse_args()
    main(args)
