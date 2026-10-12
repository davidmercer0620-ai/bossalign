# 03: Limits of the Clean-Text Helper

`sanitize_deliverable()` is a small text helper. It removes BossAlign HTML comments, `[RULE-...]` and `[EVT-...]` tags, and a few explicitly marked internal-feedback parentheticals, then normalizes repeated blank lines.

It is not a general privacy scanner. It cannot reliably identify arbitrary personal data, secrets, prompts, or business information, and it does not rewrite sentences that become awkward after a tag is removed. Do not treat it as a security review or document-export system.

```python
from bossalign.sanitizer import sanitize_deliverable

cleaned = sanitize_deliverable("Text [RULE-abc]\n\n<!-- bossalign: internal -->")
```

Applications must review external deliverables under their own data-handling rules. Rule provenance and review records stay in the SQLite memory rather than being appended to the final text.
