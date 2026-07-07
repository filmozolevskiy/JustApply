# Company Research UI prototype

**Question:** What should the **Company Research** drawer section look like (empty, researched, sparse data, loading)?

**Route:** `http://127.0.0.1:8000/prototype/company-research`

## Verdict — **Variant A (Metrics grid)**

Chosen 2026-07-06.

### Layout (researched state)

1. **Header row:** `Glassdoor Company Research` + green **G** badge link to Glassdoor overview · **Refresh** · **Wrong company?**
2. **Three metric tiles:** Size · Rating (with review count sublabel) · Recommend %
3. **Salary row:** `Base salary ({title}):` value or `n/a`
4. **Interview snippets:** up to 3 cards (difficulty · outcome + summary) — **no** separate "Interview process" heading

### Empty state

Dashed CTA panel + **Research company** button + one-line explainer.

### Loading state

Spinner + "Researching employer on Glassdoor…"

### Other UI decisions (all variants)

- Glassdoor data only — no listing/scrape size in this section
- Spend modal: editable Glassdoor job title + cached vs billable slices (see `companyResearchUiPrototype.js`)

### Reference implementation

- Markup/CSS: `src/web/static/js/prototype/companyResearchUiPrototype.js` → `renderVariantA`
- Badge SVG: `glassdoorBadgeHtml()` + `.drawer-company-glassdoor`

### Cleanup

Delete this route and prototype files when production drawer ships (`/prototype/company-research`, `prototype-company-research.css`, `companyResearchUiPrototype.js`).
