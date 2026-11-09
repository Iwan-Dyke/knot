"""Corpus-normalised lexical routing; evidence ranking remains in search.py."""

import math
from collections import Counter

from knot.retrieval_engine.ranking import _Question, tokens


def terms(text):
    # Only lexical forms are normalised. Similar terms never merge identities.
    return {
        word[:-3] + 'y'
        if len(word) > 4 and word.endswith('ies')
        else word[:-1]
        if len(word) > 4 and word.endswith('s') and not word.endswith('ss')
        else word
        for word in tokens(text)
    }


class DiscoveryQuestion(_Question):
    include_source_titles = True

    def __init__(self, question):
        super().__init__(question, [])
        self.terms = terms(question)
        self.idf = {}
        self.unseen_weight = 1

    def fit(self, texts):
        documents = [terms(text) for text in texts]
        frequency = Counter(term for document in documents for term in document)
        self.idf = {
            term: 1 + math.log((len(documents) + 1) / (count + 1))
            for term, count in frequency.items()
        }
        self.unseen_weight = 1 + math.log(len(documents) + 1)
        self.weights = {
            term: self.idf.get(term, 1 + math.log(len(documents) + 1)) for term in self.terms
        }

    def score(self, text, *, labels='', predicate=''):
        document = terms(text + ' ' + labels)
        matched = sorted(self.terms & document)
        numerator = math.fsum(self.weights[t] ** 2 for t in matched)
        query_norm = math.sqrt(math.fsum(w**2 for w in self.weights.values())) or 1
        document_norm = (
            math.sqrt(math.fsum(self.idf.get(t, self.unseen_weight) ** 2 for t in sorted(document)))
            or 1
        )
        return {
            'score': round(numerator / (query_norm * document_norm), 6),
            'matched': matched,
            'label_terms': sorted(self.terms & terms(labels)),
            'length_factor': 1,
            'predicate_bonus': 0,
            'concepts': [],
            'intents': self.intents,
        }
