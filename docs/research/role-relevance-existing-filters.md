# Role Relevance vs existing unrelated-job filters

**Date:** 2026-09-03  
**Question:** How does existing unrelated-job rejection overlap the planned Role Relevance spec? What must the spec replace, reuse, or ignore?  
**Method:** Primary sources in this repo only (code, ADRs, `CONTEXT.md`, skills). No product implementation.

Locked Role Relevance intent (spec map + glossary): the check uses the **search run’s query**, not the resume and not a Target Role field; it runs **after** the Resume Matcher; a **clear no** moves the job to **Rejected**; unsure, missing, or **Unclassified** passes; QA-family titles (SDET, Software Engineer in Test) pass for query `QA`. Auto-**Reject** on low matcher score is out of scope. Drop-before-save title filters are out of scope.

---

## 1. `reject_unrelated.py` (manual operator helper)

**Paths:** [`.claude/skills/reject-unrelated-jobs/SKILL.md`](../../.claude/skills/reject-unrelated-jobs/SKILL.md), [`.claude/skills/reject-unrelated-jobs/scripts/reject_unrelated.py`](../../.claude/skills/reject-unrelated-jobs/scripts/reject_unrelated.py). There is **no** `scripts/reject_unrelated.py` at the repo root (the research ticket’s shorthand). The skill points at the skill-folder script.

### What it does

It is **not** part of the Search & Evaluation Pipeline. It opens SQLite directly, scans titles with a regex union, and optionally `UPDATE`s `status = 'rejected'`.

**Lanes (code vs skill text):**

- Default scan: `status = 'scraped'` only (`get_unrelated_jobs`, lines 27–30 of the script).
- `--all-active`: `status != 'rejected'` (same function, lines 27–28).
- The skill still says the default lane is **`sourced`** (SKILL.md lines 23–24). CLI help still says “just `'sourced'` jobs” (script lines 61). **`sourced` is a legacy lane name**; live code queries **`scraped`**.

**Keywords:** English and French title tokens, word-bounded, **union of four career families** — QA, PM, Data, AI — compiled as one regex (script lines 12–21, 35–38). A job is “unrelated” when the **title matches none** of those families. Company and description are not scanned.

**Confirmation:**

- The **skill** requires the agent to show a table and get **explicit user confirmation** before any DB update (SKILL.md lines 31–33).
- The **script** does **not** prompt. `--list` (default) is dry-run. `--reject-all` rejects every current candidate immediately (script lines 76–81). `--reject-ids` writes the given IDs even if they were not in the candidate list (script lines 83–85, `reject_jobs` 43–54).

**Bilingual titles:** FR tokens exist (`qualité`, `automatique`, `projet`, `données`, `analyste`, `ia`, `générative`, etc., script lines 14–20). Role Relevance’s spec map still lists French/bilingual titles as **not yet specified**.

### Overlap with Role Relevance

Surface overlap: both can move cards to **Rejected** because the listing is “the wrong kind of job.” Semantics do **not** match.

| | `reject_unrelated` | Role Relevance (locked) |
| --- | --- | --- |
| Target | Fixed union: AI ∪ Data ∪ QA ∪ PM | **This search query** (e.g. `QA`) |
| When | Manual, after jobs already sit in Scraped (or any non-Rejected) | After Resume Matcher writeback |
| Signal | Title regex only | Listing vs query; clear-no only |
| QA family | `sdet` is in the QA keyword list | SDET / Software Engineer in Test **must pass** for query `QA` |
| Cross-family | A Product Manager title is **kept** (PM keywords) | For query `QA`, a developer or PM role is a **clear no** |

So the helper cannot stand in for Role Relevance. A QA search that scraped a “Senior Product Manager” would **survive** `reject_unrelated` and would **fail** Role Relevance.

---

## 2. Does matcher score ever Reject?

**No.** `matchScore`, `matchType`, and `shouldProceed` are stored fields. They do not choose the Kanban lane.

Resume Matcher JSON contract (`src/core/matcher.py` `_build_prompt`, lines 48–65):

- `matchScore` 0–100  
- `matchType` `"match"` | `"no-match"`  
- `shouldProceed` boolean  
- Rule: `matchScore >= 75` ⇒ `matchType` is `"match"` and `shouldProceed` is true  
- Also classifies `remoteType`, `seniority`, `employmentType`, recruiter flag, salary, summary  

Recruiter handling (prompt lines 81–83; post-process in `evaluate_job` lines 151–160 and the same logic in `batch_poller.parse_evaluation_text` lines 152–163): agency listings get `shouldProceed = false`, `matchType = "no-match"`, and a score penalty. Still **no lane change** in that code.

**Writeback** (`src/core/batch_poller.py` `write_back_job_evaluation`, lines 469–530):

1. Skip if the row is not still `scraped` (486–487).  
2. Persist matcher fields including score / `matchType` / `shouldProceed` (495–513).  
3. Lane = `matched` if `passes_attribute_gate(...)` else `rejected` (515–530).  

`matchType` and `shouldProceed` are copied into the row and **never read** for that status decision.

**Unclassified poison fallback** (`apply_unclassified_fallback`, lines 389–442): forces `matchScore: 0`, `matchType: "no-match"`, `shouldProceed: False`, `unclassified: True`, then **only** the attribute gate decides `matched` vs `rejected`.

**Reassess** (`src/pipelines.py` `run_reassess_pipeline`, lines 347–396): same pattern — persist matcher fields, demote Scraped/Matched to Rejected **only** when the attribute gate fails. Low score / `no-match` does not demote.

Pipeline-owned `update_job_status(..., "rejected")` call sites are only:

- `batch_poller.apply_unclassified_fallback` (line 441)  
- `batch_poller.write_back_job_evaluation` (line 529)  
- `pipelines.run_reassess_pipeline` (line 396)  

All three are attribute-gate failures, not matcher-score failures.

This matches `CONTEXT.md` Role Relevance and the spec map: resume fit stays a score; auto-Reject on low score is out of scope.

---

## 3. How the attribute gate Rejects

**Module:** `src/core/attribute_gating.py`.

`passes_attribute_gate` (lines 79–119) returns false when **any** active preference fails:

- Remote type vs allowed remote types (when not “any”)  
- Seniority vs allowed seniorities (when not “any”)  
- Employment Type vs selected types (when not “any”)  
- Salary Min vs `annualMax` (when Min is set; missing band **passes**, lines 56–62)

`CONTEXT.md` **Attribute-filtered Job** (lines 59–61): evaluated job whose merged remote / seniority / Employment Type / Salary Min fails → **Rejected**. Distinct from scraper post-filters and from Role Relevance.

`CONTEXT.md` **Fallback-rejected Job** (lines 63–64): same gate on **scraper** attributes after matcher never returned a valid result (Unclassified poison). Counted separately in Task Logs.

`CONTEXT.md` **Role Relevance** (lines 55–57): explicitly **distinct** from that attribute gate.

`is_unclassified` (attribute_gating.py lines 170–172): empty evaluation dict only. Role Relevance’s locked rule (Unclassified **passes** the role check) is the opposite of “fail closed.” The attribute gate still **can** Reject Unclassified jobs via scraper attributes (`apply_unclassified_fallback`). The spec must not reuse that fail-closed behavior for the role check.

Task Logs today count `attribute-filtered` and `fallback-rejected` only (`batch_poller.py` `_chunk_summary_line` / `_round_summary_line`, lines 193–221). Role Relevance rejects would need a **new bucket** unless the spec says they share Attribute-filtered (glossary currently forbids that).

---

## 4. ADR 0008 vs current save-then-batch flow

**ADR 0008** (`docs/adr/0008-llm-attribute-classification.md`, Decision items 2 and 5, lines 17–25):

- Intended flow: scrape → deduplicate → Resume Matcher → attribute check → **save**.  
- Mismatch: jobs are **not saved**. Log `Attribute mismatch: …`.  
- Full matcher `{}`: scraper fallback, gate, save with empty match fields if the gate passes.

**Current pipeline** (`CONTEXT.md` **Search & Evaluation Pipeline**, lines 31–32; `src/pipelines.py` `run_search_pipeline`):

1. Scrape (company size and Employment Type post-filters still **before** save).  
2. Deduplicate.  
3. **Save immediately** as `status = "scraped"` with empty `matchType` (pipelines.py lines 165–181).  
4. Submit Batch Evaluation Jobs and **return** (lines 196–215). Docstring at line 69 still says “evaluate, attribute-gate, and save”; the body does **not** evaluate or gate before insert.  
5. Batch Poller later writes scores: **Scraped → Matched**, or **Rejected** on attribute-gate failure (`CONTEXT.md` Batch Poller, lines 51–52).

`mock_eval` still skips gating at search time (pipelines.py lines 139–140, 174–179) and saves Scraped rows without a batch.

ADR 0008’s “do not persist mismatches” is **already superseded** by save-then-batch + post-writeback Reject. Role Relevance is locked to that later shape: **no drop-before-save**, fail → **Rejected** after matcher.

---

## 5. Implications for the Role Relevance spec

### Replace

- **Do not treat `reject_unrelated.py` as the product gate.** Different target (four-family union vs search query), different time (manual title scan vs post-matcher), different confirmation model. If operators still want a bulk title cleanup, keep it as a skill/script; the spec should not absorb its regex union as the Role Relevance definition.
- **Do not restore ADR 0008 drop-before-save** for role mismatch. Glossary and map already forbid it.
- **Do not encode Role Relevance as `matchType` / `shouldProceed` / score threshold.** Those fields already mean resume (and recruiter) fit and never Reject. Reusing them would collide with stored scores and with the map’s “score still stored” open question — the answer from code is: **keep storing them; add a separate check**.

### Reuse

- **Lane change after evaluation:** same seam as the attribute gate — persist matcher JSON, then `update_job_status` to `rejected` when the **role** check is a clear no. Primary hook: `write_back_job_evaluation` (`batch_poller.py` 469–530). Mirror on `run_reassess_pipeline` if Reassess should apply Role Relevance (query source is a separate ticket).
- **Order:** Resume Matcher first, then attribute merge/gate, then Role Relevance (or Role Relevance immediately after matcher JSON, still after scrape-save). Either way, do not reject before the row exists in **Scraped**.
- **Unclassified / empty matcher:** Role Relevance **passes** (locked). Reuse `is_unclassified` / empty evaluation as “do not role-reject.” Do **not** copy attribute-gate fail-closed on scraper attributes for the role check.
- **QA-family pass for query `QA`:** the skill keyword list already includes `sdet`, `test`, `testing`, `qa`. That list is **too wide** (also PM/Data/AI) and **title-only**, but the SDET token is a useful example for the spec’s include set — not a drop-in classifier.
- **Task Logs pattern:** new counter + optional per-job line, analogous to Attribute-filtered vs Fallback-rejected — do not dump role fails into `attribute-filtered` (glossary: Role Relevance ≠ attribute gate).

### Ignore

- **`reject_unrelated` default `sourced` wording** and `--reject-all` without a prompt — operator-skill details, not pipeline contract.
- **Title-only EN/FR regex as the v1 classifier**, unless the spec later chooses keywords as a prototype. The map still has French titles unspecified; copying the helper’s FR list would still be a **union-of-families** filter, which is the wrong question.
- **Low `matchScore` / `no-match` / recruiter `shouldProceed: false` as Role Relevance.** Recruiter penalty stays matcher behavior (`CONTEXT.md` Resume Matcher, line 28).
- **Scraper post-filters** (company size, Employment Type before save) — already distinct in the glossary.
- **A Job.searchQuery column** — `src/schemas.py` `Job` has no search-query field (lines 57–78). Needed for backfill/reassess Role Relevance; not provided by `reject_unrelated`. Out of this overlap question except: the helper does not solve “which query?” either.

### Spec must still decide (not answered by existing filters)

- Kanban / drawer copy for a Role Relevance reject (map: not yet specified).  
- Interaction copy: score and `matchType` remain on the Rejected card after a role fail (code already stores them before attribute Reject).  
- Whether Role Relevance runs if the attribute gate already failed (both would Reject; order only affects Task Log buckets).  
- French / bilingual titles.  
- Query identity on backfill and reassess (no stored query today).
