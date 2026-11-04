# Generated from Companion Core 30628cff61d6642d6ababf833d6432cd83695c0f; see provenance/upstream.json.
# SPDX-License-Identifier: MIT
# ruff: noqa: E501
import math
import re
from collections import Counter

_PUNCT = re.compile('[\\s，。！？、；：“”‘’（）()《》【】\\[\\],.!?;:\'\\"…—-]+')
_WEEKEND = re.compile('(?:周|星期|礼拜)[六日天]')
_WEEKDAY = re.compile('(?:周|星期|礼拜)[一二三四五]')

def _grams(text):
    text = _PUNCT.sub('', text.lower())
    return [text[i:i + 2] for i in range(len(text) - 1)] or ([text] if text else [])

def expand(query):
    """Add the calendar class of named days for the lexical channel only: a rule stated
    as 工作日/周末 shares no characters with a question about 周六 or 周二."""
    extra = []
    if _WEEKEND.search(query):
        extra.append('周末')
    if _WEEKDAY.search(query):
        extra.append('工作日')
    if '周末' in query:
        extra += ['周六', '周日']
    if '工作日' in query:
        extra += ['周一', '周五']
    return ' '.join([query, *extra])

def lexical(query, docs, *, bags=None):
    """BM25 over character bigrams; Chinese needs no tokenizer for this."""
    terms = set(_grams(query))
    if bags is None:
        bags = [Counter(_grams(doc)) for doc in docs]
    if not terms or not bags:
        return [0.0] * len(docs)
    average = sum((sum(bag.values()) for bag in bags)) / len(bags) or 1
    frequency = Counter((term for bag in bags for term in terms if term in bag))
    scores = []
    for bag in bags:
        length, score = (sum(bag.values()), 0.0)
        for term in terms:
            if term in bag:
                idf = math.log(1 + (len(bags) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                tf = bag[term]
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / average))
        scores.append(score)
    return scores

def _ranked(scores):
    return [index for index, _ in sorted(enumerate(scores), key=lambda item: -item[1])]

def merge(first, hop, limit, extra):
    """Final picks after filtering: the two seeds, then up to `extra` second-hop docs
    not already chosen, then the rest of the first hop. Byte trimming drops from the
    end, so the weakest first-hop docs go before the chained evidence."""
    if limit <= 0:
        return []
    head = first[:max(1, limit - extra)]
    chained = [index for index in hop if index not in head][:extra]
    order = head[:2] + chained + head[2:]
    order += [index for index in first if index not in order]
    return order[:limit]

def fuse(lexical, semantic):
    """Reciprocal rank fusion, independent of the two scorers' numeric scales."""
    scores = {}
    for ranking in (lexical, semantic):
        for rank, key in enumerate(ranking, 1):
            scores[key] = scores.get(key, 0) + 1 / (60 + rank)
    return scores
