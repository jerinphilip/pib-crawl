import os
from argparse import ArgumentParser
from io import StringIO

import numpy as np
from ilmulti.segment import build_segmenter
from sqlalchemy import and_, func
from tqdm import tqdm

from .. import db
from ..models import Entry


class WriteStrategy:
    def __init__(self, fpath):
        self.fpath = fpath
        self._file = open(self.fpath, "w")

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self._file.close()


class RawDump(WriteStrategy):
    def add_content(self, content):
        print(content, file=self._file)


class Segmented(WriteStrategy):
    def __init__(self, fpath):
        super().__init__(fpath)
        self.unique = set()

        # TODO(jerin): Remove this hacky two lines.
        self.segmenter = build_segmenter("pattern")

    def add_content(self, content):
        lang, segments = self.segmenter(entry.content, lang=args.lang)
        self.unique.update(segments)

    def __exit__(self, *args, **kwargs):
        for sample in self.unique:
            print(sample, file=self._file)
        self._file.close()


def export(args):
    fpath = "{}.{}".format(args.prefix, args.lang)

    Strategy = Segmented if args.segment else RawDump
    with Strategy(fpath) as strategy:
        entries = db.session.query(Entry).filter(Entry.lang == args.lang).all()

        for entry in tqdm(entries):
            if entry.content:
                strategy.add_content(entry.content)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--lang", help="language of mono corpus", required=True)
    parser.add_argument(
        "--prefix", help="prefix to the filename, lang is appended", required=True
    )
    parser.add_argument(
        "--segment",
        action="store_true",
        help="Segment lines or not using available segmenter, also enables unique.",
    )
    args = parser.parse_args()
    export(args)
