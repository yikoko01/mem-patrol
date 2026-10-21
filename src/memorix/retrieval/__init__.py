"""Recall scorer (M1.5): deterministic lexical retrieval extracted from patrol.

Design choices approved as default: lexical (zero runtime deps, optional jieba
for anchors) first; a ``vector`` provider seam is documented for later.
"""
from .score import recall, recall_scored
from .store import RetrievalRow, doc_freq, load_rows

__all__ = ["RetrievalRow", "doc_freq", "load_rows", "recall", "recall_scored"]
