"""Optional detector adapters; importing this package loads no model runtime."""

from .lettuce import LettuceDetectAdapter
from .minicheck import MiniCheckAdapter
from .alignscore import AlignScoreAdapter
from .relevance import LexicalQuestionRelevance, RerankerQuestionRelevance
from .summac import SummaCAdapter

__all__ = [
    "AlignScoreAdapter",
    "LettuceDetectAdapter",
    "MiniCheckAdapter",
    "LexicalQuestionRelevance",
    "RerankerQuestionRelevance",
    "SummaCAdapter",
]
