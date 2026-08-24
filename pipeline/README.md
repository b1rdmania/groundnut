# Legacy compatibility pipeline

This directory preserves the original CUAD contract-extraction path. It remains
covered by tests and is still imported by `groundnut.engine`, but it is not the
current IC research product path and its historical gate is not Groundnut's
product acceptance test.

Keep behaviour stable unless a compatibility fixture demonstrates a defect.
New IC-loop work belongs in the canonical `groundnut` path.
