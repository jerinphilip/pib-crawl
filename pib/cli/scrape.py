import json
import logging
import os
import re
import sys
from argparse import ArgumentParser
from copy import deepcopy
from datetime import datetime
from urllib.request import Request, urlopen

import langid
from bs4 import BeautifulSoup
from tqdm import tqdm, trange

from .. import db
from ..models import Entry


class PIBArticle:
    def __init__(self, Id, lang, place, content, links, date):
        self.Id = Id
        self.lang = lang
        self.date = date
        self.place = place
        self.content = content
        self.links = links

    def as_dict(self):
        return (
            {
                "id": self.Id,
                "lang": self.lang,
                "date": self.date,
                "place": self.place,
                "content": self.content,
            },
            self.links,
        )

    def __repr__(self):
        return "PIB(Id={}, lang={}, date={}, place={}, links={})".format(
            self.Id, self.lang, str(self.date), self.place, self.links.__repr__()
        )

    @classmethod
    def fromCrawl(cls, _dict):
        Id = _dict["Id"]
        parsedContent = PIBArticle.parseContent(Id, _dict["content"])
        parsedDate = PIBArticle.parseDate(Id, _dict["date"])
        return cls(
            Id=_dict["Id"],
            lang=parsedContent["lang"],
            place=parsedDate["place"],
            content=parsedContent["content"],
            links=_dict["links"],
            date=parsedDate["date"],
        )

    @staticmethod
    def parseDate(Id, release_subhead):
        line = release_subhead.replace("\r\n", "").strip()
        pattern = re.compile(
            "([0-9]*) ([A-Z]*) ([0-9]*) ([0-9]*:[0-9]*[AP]M) by PIB (.*)"
        )
        matches = pattern.search(line)
        if matches:
            day, month, year, time, place = matches.groups()
            date_string = f"{month} {day} {year} {time}"
            date = datetime.strptime(date_string, "%b %d %Y %I:%M%p")
            return {"date": date, "place": place}
        else:
            logging.error("Failed on date-parse {}".format(Id))
            return None

    @staticmethod
    def parseContent(Id, text):
        # text = body.text
        lang, *_ = langid.classify(text)
        lines = text.strip().split("\n")

        def _filter(text):
            flag = True
            garbage = ["Posted On:", "by PIB", "ID:", "/"]
            for fil in garbage:
                if fil in text:
                    flag = True
            return flag

        output = []
        for line in lines:
            line = line.strip()
            if line and _filter(line):
                output.append(line)
        content = "\n".join(output)
        content = content.lstrip().rstrip()
        return {"lang": lang, "content": content}


class CachedCrawler:
    headers = {
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.131 Safari/537.36",
        "referrer": "https://google.com",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self, path, redo=False):
        self.redo = redo

    def retrieve_pib_article(self, key):
        try:
            page = self.load(key)

            # pytype: disable=attribute-error
            soup = BeautifulSoup(page, "html.parser")
            lang_links = soup.find("div", {"class": "ReleaseLang"})

            def process(link):
                prefix, Id = link.split("=")
                return Id

            links = (
                {}
                if lang_links is None
                else {
                    a.text.strip(): process(a["href"])
                    for a in lang_links.find_all("a", href=True)
                }
            ) 
            content = soup.find("div", {"id": "PdfDiv"})
            text = content.text.strip()

            date = soup.find(
                "div", {"class": "ReleaseDateSubHeaddateTime"}
            ).text.strip()
            ministry = soup.find("div", {"class": "MinistryNameSubhead"}).text.strip()

            # pytype: enable=attribute-error

            return PIBArticle.fromCrawl(
                {
                    "Id": key,
                    "content": text,
                    "date": date,
                    "ministry": ministry,
                    "links": links,
                }
            )

        except Exception as e:
            logging.debug("Article: {key} failed with {msg}".format(key=key, msg=e))
            return None

    def load(self, key):
        url = "https://pib.gov.in/PressReleasePage.aspx?PRID={}".format(key)
        request = Request(url, headers=self.headers)
        web_byte = urlopen(request).read()
        web_page = web_byte.decode("utf-8")
        return web_page


class AdjacencyList(dict):
    def __init__(self, path):
        self.path = path

    def load(self):
        if os.path.exists(self.path):
            with open(self.path) as fp:
                self.update(json.load(fp))
        return self

    def save(self):
        with open(self.path, "w+") as fp:
            return json.dump(self, fp)


def main(args):
    crawler = CachedCrawler(args.path, args.force_redo)
    adj = AdjacencyList("{}.save.adj.json".format(args.path))
    adj = adj.load()

    def binary_search_find_start(adj, begin, end):
        while begin < end:
            idx = int((begin + end) / 2)
            key = str(idx)
            entry = Entry.query.get(key)
            if (entry is None) or (key not in adj):
                end = idx - 1
            else:
                begin = idx + 1
        return begin

    begin = binary_search_find_start(adj, args.begin, args.end)
    for idx in trange(begin, args.end):
        key = str(idx)
        entry = Entry.query.get(key)
        if (entry is None) or (key not in adj):
            payload = crawler.retrieve_pib_article(key)
            if payload is not None:
                processed, links = payload.as_dict()
                adj[key] = deepcopy(links)
                if entry is None:
                    entry = Entry(**processed)
                    db.session.add(entry)
                    logging.info("Idx({}) Final: {}".format(key, payload))
        else:
            logging.info("Idx({}) exists in db".format(key))

        if (idx + 1 - args.begin) % args.commit_interval == 0:
            db.session.commit()
            db.session.flush()
            adj.save()
            logging.info("Committing to DB @ {}".format(key))

    db.session.commit()
    db.session.flush()
    adj.save()


def setup_logging(logPath, fileName):
    logFormatter = logging.Formatter(
        "%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s"
    )
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.DEBUG)

    fileHandler = logging.FileHandler(".".join([logPath, fileName]))
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)

    # consoleHandler = logging.StreamHandler(sys.stdout)
    # consoleHandler.setFormatter(logFormatter)
    # rootLogger.addHandler(consoleHandler)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--path", help="path to lmdb save location", type=str, required=True
    )
    parser.add_argument("--begin", help="Begin PIB ID", type=int, required=True)
    parser.add_argument("--end", help="End PIB ID", type=int, required=True)
    parser.add_argument(
        "--force-redo", help="Ignore if already exists anywhere", action="store_true"
    )
    parser.add_argument(
        "--commit-interval", help="Transaction commit interval", type=int, default=1000
    )
    args = parser.parse_args()
    setup_logging(args.path, "crawl.log")
    main(args)
