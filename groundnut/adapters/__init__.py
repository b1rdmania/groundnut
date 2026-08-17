"""Optional detector adapters; importing this package loads no model runtime."""

from .lettuce import LettuceDetectAdapter
from .minicheck import MiniCheckAdapter

__all__ = ["LettuceDetectAdapter", "MiniCheckAdapter"]
