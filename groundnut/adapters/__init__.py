"""Optional detector adapters; importing this package loads no model runtime."""

from .lettuce import LettuceDetectAdapter
from .minicheck import MiniCheckAdapter
from .alignscore import AlignScoreAdapter

__all__ = ["AlignScoreAdapter", "LettuceDetectAdapter", "MiniCheckAdapter"]
