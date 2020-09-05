import os
from io import StringIO
from argparse import ArgumentParser
from langid.langid import LanguageIdentifier
from langid.langid import model as m
from ilmulti.translator import from_pretrained
from ..cli.utils import Preproc, ParallelWriter

class LengthRatioFilter:
    def __init__(self, tokenizer, min_length, lower_bound, upper_bound):
        self.lower_bound = lower_bound
        self.upper_bound = upper_bound
        self.tokenizer = tokenizer
        self.min_length = min_length
    
    def __call__(self, src_line, tgt_line):
        _, src_tokens = self.tokenizer(src_line, lang=src_lang)
        _, tgt_tokens = self.tokenizer(tgt_line, lang=tgt_lang)
        src_len, tgt_len = len(src_tokens), len(tgt_tokens)

        # Also handles the zero degeneracy
        src = (src_len >= self.min_length)
        tgt = (tgt_len >= self.min_length)
        if not (src and tgt):
            return False

        ratio = src_len/tgt_len
        return (self.lower_bound <= ratio) and (ratio <= self.upper_bound)


class EvalLang:
    def __init__(self, src_lang, tgt_lang, threshold=0.8):
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.identifier = LanguageIdentifier.from_modelstring(m, norm_probs=True)
        self.identifier.set_languages([src_lang, tgt_lang])
        self.threshold = threshold

    def __call__(self, src_line, tgt_line):
        slang, src_prob = self.identifier.classify(src_line)
        tlang, tgt_prob = self.identifier.classify(tgt_line)
        src = (src_prob >= self.threshold)
        tgt = (tgt_prob >= self.threshold)
        if (slang == self.src_lang and tlang==self.tgt_lang and src and tgt):
            return True
        else:
            return False


def filter_lines(src_lang, src_aligned, tgt_lang, tgt_aligned, filters):
    unfilt, aligned = set(), set()
    src_filt, tgt_filt = set(), set()
    
    for src_line, tgt_line in zip(src_aligned, tgt_aligned):
        src_line = src_line.rstrip('\n')
        tgt_line = tgt_line.rstrip('\n')

        # Check if any of the filters fail.
        for _filter in filters:
            if not _filter(src_line, tgt_line):
                continue

        # Otherwise.
        if (src_line, tgt_line) not in aligned:
            '''
            Filtering duplicates from aligned content.
            Done here as export is done per entry.
            '''
            aligned.add((src_line, tgt_line))
            unique_aligned.write(src_lang, tgt_lang, src_line, tgt_line)

        if (
            len_eval and lang_eval and 
            src_line not in src_filt and 
            tgt_line not in tgt_filt
        ):    
            src_filt.add(src_line)
            tgt_filt.add(tgt_line)
            filtered.write(src_lang, tgt_lang, src_line, tgt_line)
        
        elif (src_line, tgt_line) not in unfilt:
            unfilt.add((src_line, tgt_line))
            unfiltered.write(src_lang, tgt_lang, src_line, tgt_line)                    

if __name__ == '__main__':
    parser=ArgumentParser()
    parser.add_argument('--output-dir', help='Output-directory', type=str, required=True)
    parser.add_argument('--src-lang', help='source language, non-english', required=True)
    parser.add_argument('--tgt-lang', help='target language', default='en')
    parser.add_argument('--model', help='translation model for generating dataset', default='mm-to-en-iter2')
    args = parser.parse_args()
    model = args.model

    engine = from_pretrained(tag=model, use_cuda=False)

    fpath = os.path.join(args.output_dir, args.model)
    dirname = '{}-{}'.format(*sorted([args.src_lang, args.tgt_lang]))

    unique_aligned = ParallelWriter(fpath, fname='unique_aligned')
    filtered = ParallelWriter(fpath, fname='filtered')
    unfiltered = ParallelWriter(fpath, fname='unfiltered')
    
    src_aligned = open(os.path.join(fpath, dirname, 'aligned.{}'.format(src_lang)), 'r')
    tgt_aligned = open(os.path.join(fpath, dirname, 'aligned.{}'.format(tgt_lang)), 'r')
    
    filters = [
        EvalLang(args.src_lang, args.tgt_lang),
        LengthRatioFilter(engine.tokenizer, min_length=2, lower_bound=0.5, upper_bound=2.0)
    ]

    filter_lines(args.src_lang, src_aligned, args.tgt_lang, tgt_aligned, filters)

