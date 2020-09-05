import os
from io import StringIO
from argparse import ArgumentParser
from langid.langid import LanguageIdentifier
from langid.langid import model as m
from ilmulti.translator import from_pretrained
from ..cli.utils import Preproc, ParallelWriter

def eval_len_ratio(src_len, tgt_len):
    if src_len==0 or tgt_len==0:
        return False
    ratio = src_len/tgt_len
    src = (src_len >=2)
    tgt = (tgt_len >=2)
    if 0.5 <= ratio <= 2 and src and tgt:
        return True
    else:
        return False

class EvalLang:
    def __init__(self, src_lang, tgt_lang, threshold=0.8):
        self.identifier = LanguageIdentifier.from_modelstring(m, norm_probs=True)
        self.identifier.set_languages([src_lang, tgt_lang])
        self.threshold = threshold

    def __call__(self, src_lang, src_line, tgt_lang, tgt_line):
        slang, src_prob = self.identifier.classify(src_line)
        tlang, tgt_prob = self.identifier.classify(tgt_line)
        src = (src_prob >= self.threshold)
        tgt = (tgt_prob >= self.threshold)
        if slang==src_lang and tlang==tgt_lang and src and tgt:
            return True
        else:
            return False


def filter_lines(src_lang, src_aligned, tgt_lang, tgt_aligned):
    unfilt, aligned = set(), set()
    src_filt, tgt_filt = set(), set()
    eval_lang = EvalLang(src_lang, tgt_lang)
    
    for src_line, tgt_line in zip(src_aligned, tgt_aligned):
        _, src_tokens = tokenizer(src_line, lang=src_lang)
        _, tgt_tokens = tokenizer(tgt_line, lang=tgt_lang)

        src_len, tgt_len = len(src_tokens), len(tgt_tokens)

        len_eval = eval_len_ratio(src_len, tgt_len)
        lang_eval = eval_lang(src_lang, src_line, tgt_lang, tgt_line)
        
        src_line = src_line.rstrip('\n')
        tgt_line = tgt_line.rstrip('\n')

        if (src_line, tgt_line) not in aligned:
            '''
                Filtering duplicates from aligend content.
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
    src_lang, tgt_lang = args.src_lang, args.tgt_lang
    model = args.model

    engine = from_pretrained(tag=model, use_cuda=False)
    tokenizer = engine.tokenizer

    fpath = os.path.join(args.output_dir, args.model)
    dirname = '{}-{}'.format(*sorted([src_lang, tgt_lang]))

    unique_aligned = ParallelWriter(fpath, fname='unique_aligned')
    filtered = ParallelWriter(fpath, fname='filtered')
    unfiltered = ParallelWriter(fpath, fname='unfiltered')
    
    src_aligned = open(os.path.join(fpath, dirname, 'aligned.{}'.format(src_lang)), 'r')
    tgt_aligned = open(os.path.join(fpath, dirname, 'aligned.{}'.format(tgt_lang)), 'r')
    
    filter_lines(src_lang, src_aligned, tgt_lang, tgt_aligned)

