"""Presentation-layer formatting and tag stripping helper.

SECURITY NOTICE:
This module is strictly a presentation-layer string utility for cleaning internal
markup tags. It is NOT a security boundary, privacy scanner, or DLP mechanism.
Data privacy and isolation are enforced architecturally by local-first storage
and the whitelist-driven PrivacyExporter. Do not rely on regular expressions to
de-identify sensitive data.
"""

import re


def sanitize_deliverable(content: str) -> str:
    """
    Remove selected BossAlign tags, internal feedback markers, and normalize blank lines.

    This is a small presentation text helper, not a general privacy or metadata scanner.
    """
    # 1. Strip HTML-like comments <!-- bossalign: ... -->
    content = re.sub(r"<!--\s*bossalign:.*?-->", "", content, flags=re.DOTALL)
    
    # 2. Strip explicit internal tags like [RULE-...] or [EVT-...]
    content = re.sub(r"\[RULE-[^\]]+\]", "", content)
    content = re.sub(r"\[EVT-[^\]]+\]", "", content)
    
    # 3. Strip internal references like (Based on reviewer feedback...)
    content = re.sub(r"（根据[^）]*反馈[^）]*）", "", content)
    content = re.sub(r"\(Based on [^\)]* feedback\)", "", content, flags=re.IGNORECASE)
    
    # 4. Normalize multiple blank lines into standard double newlines
    content = re.sub(r"\n{3,}", "\n\n", content)
    
    return content.strip()
