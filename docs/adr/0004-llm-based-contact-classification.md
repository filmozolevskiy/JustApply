# LLM-based contact classification replaces field and keyword matching

The Contact Sample (~100 Apify profiles) is classified by a single batch LLM call (Gemini) using each contact's name, headline, languages, current position, and location. This replaces two deterministic approaches: a `languages` field set intersection for Russian Speaker detection and an `HR_TITLE_KEYWORDS` list for recruiter detection.

The keyword list missed titles like "Senior Talent Acquisition Partner" and required manual maintenance as LinkedIn title conventions drift. The LLM handles nuanced titles, multilingual signals, and both Outreach Audience types in one pass — at the cost of added latency and LLM token spend per enrichment.

## Considered Options

- **Keep field lookup for Russian Speakers, add keyword matching for Recruiters** — deterministic and cheap, but brittle. Title conventions change; the keyword list needs ongoing maintenance and still misclassifies edge cases.
- **Per-contact LLM calls** — maximum flexibility, but 100 calls per enrichment is prohibitively slow and expensive.
- **Single batch LLM call (chosen)** — one prompt with all 100 contacts, structured output. Accurate, fast enough (one round-trip), and extensible to new Outreach Audience types without code changes.
