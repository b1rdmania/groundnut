TEMPLATE = """You are assisting a legal due-diligence review of a contract
excerpt. Read the excerpt below and identify any spans of text that fall
under the clause categories listed below.

Copy matching spans exactly as they appear in the excerpt - never paraphrase,
summarize, or invent text. If a category has no matching clause in this
excerpt, leave it out entirely.

Span boundaries matter: copy the single sentence that carries the finding -
not the paragraph around it, and not a bare fragment shorter than a sentence.
Do not merge neighboring sentences into one quote unless the finding itself
only makes sense as a run-on across a sentence boundary (e.g. a defined term
split by a semicolon). When a paragraph contains more than one distinct
finding, return each as its own separate quote rather than one quote covering
the whole paragraph.

Respond with a single JSON object with two top-level keys. checked_categories
must list every category you evaluated in this source segment. findings maps
each category name to a list of the verbatim spans you found for it. Use an
empty list when nothing applies. Output JSON only - no prose, no markdown
fences. An omitted acknowledgement is treated as an incomplete check, never
as a clear result.

JSON SHAPE:
{{"checked_categories": ["<each evaluated category>"], "findings": {{"<category>": ["<verbatim span>"]}}}}

CATEGORIES:
{categories}

CONTRACT TEXT:
{chunk}
"""


def build_prompt(categories, chunk, domain=None):
    """Build the legacy prompt or a domain-pack-specific variant.

    Calls without ``domain`` remain byte-for-byte compatible with the legacy
    evaluation runs. A domain pack changes only job-specific framing,
    category descriptions, and the noun used for the source document.
    """
    if domain is None:
        cat_list = "\n".join("- " + c for c in categories)
        return TEMPLATE.format(categories=cat_list, chunk=chunk)

    noun = domain.document_noun
    return f"""{domain.extract_context}

Copy matching spans exactly as they appear in the {noun} - never paraphrase,
summarize, or invent text. If a category has no matching clause in this
{noun}, leave it out entirely.

Span boundaries matter: copy the single sentence that carries the finding -
not the paragraph around it, and not a bare fragment shorter than a sentence.
Do not merge neighboring sentences into one quote unless the finding itself
only makes sense as a run-on across a sentence boundary. When a paragraph
contains more than one distinct finding, return each as its own separate quote.

Respond with a single JSON object with one top-level key, findings, whose
value maps each category name to a list of the verbatim spans you found for
it. Use an empty list when nothing applies. Output JSON only - no prose, no
markdown fences.

CATEGORIES:
{domain.category_block()}

{noun.upper()} TEXT:
{chunk}
"""
