"""Optional detector adapters; importing this package loads no model runtime."""

from .lettuce import LettuceDetectAdapter
from .minicheck import MiniCheckAdapter
from .alignscore import AlignScoreAdapter
from .relevance import (
    ExtractiveQuestionAnswerRelevance,
    LexicalQuestionRelevance,
    RerankerQuestionRelevance,
)
from .summac import SummaCAdapter

__all__ = [
    "AlignScoreAdapter",
    "ExtractiveQuestionAnswerRelevance",
    "LettuceDetectAdapter",
    "MiniCheckAdapter",
    "LexicalQuestionRelevance",
    "RerankerQuestionRelevance",
    "SummaCAdapter",
]
