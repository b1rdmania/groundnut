CHUNK_CHARS = 20000
OVERLAP_CHARS = 500


def chunk_text(text):
    if len(text) <= CHUNK_CHARS:
        return [text]
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + CHUNK_CHARS, n)
        chunks.append(text[start:end])
        if end == n:
            break
        start = end - OVERLAP_CHARS
    return chunks
