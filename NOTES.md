# UI Prototype Notes: Job Hunter Dashboard

This directory contains a throwaway UI prototype exploring layouts and interactions for the new FastAPI-based job tracker dashboard.

## Context & Question

We are planning to migrate the Job Hunter database from Google Sheets to a local SQLite database and wrap it in a single-page web dashboard. The prototype was built to answer:
> **"What should the new local dashboard look like and how should it feel to track jobs and applications?"**

We generated **three radically different UI variations** on a single web interface, switchable via a URL search param or a floating bottom bar.

## The Three Variants

1. **Variant A: Command Center (`?variant=A`)**
   - *Concept*: A split-pane grid layout. Left pane holds search configurations and a scrolling terminal-style log stream. Right pane is a high-density, structured spreadsheet-style table showing jobs, search score metrics, and status badges.
   - *Best For*: High-density scanning, developer-first command room monitoring, and trigger actions.

2. **Variant B: Kanban Board (`?variant=B`)**
   - *Concept*: Standard agile project management board with lanes representing stages (`Sourced`, `Evaluating`, `Applied`, `Contacted`, `Interviewing`). Includes card action movements and a side drawer for detailed job description/outreach previews.
   - *Best For*: Tracking the lifestyle stages of applications visually.

3. **Variant C: Split Feed & Analytics (`?variant=C`)**
   - *Concept*: Analytics overview ribbon on top, with a 2-column split feed layout below (comparable to modern email clients). Selecting a job card on the left loads a rich, full-screen detail workspace on the right, housing LLM match breakdowns and copy/regenerate buttons for outreach emails.
   - *Best For*: Evaluating specific job descriptions and drafting/managing personalized letters.

---

## How to Run the Prototype

To start the local FastAPI web server:

```bash
# Start the Uvicorn server (port 8000)
.venv/bin/python3 prototype_dashboard.py
```

Then navigate to:
**[http://127.0.0.1:8000/?variant=A](http://127.0.0.1:8000/?variant=A)**

### Interactive Features Built-in:
- **Variant Switcher**: Use the bottom floating bar or the `←` / `→` arrow keys to cycle layouts.
- **Active Resume Switcher**: Switch the active profile (e.g. `qa.md` or `project_manager.md`) in the header; see its impact on match scoring and logs.
- **Mock Scraping Task (SSE)**: Clicking "Trigger Scraping Run" establishes an EventSource connection to the FastAPI backend, streaming simulated scraper and evaluation logs line-by-line, and injecting new job elements directly into the state on completion.
- **Card Promotion & State Sync**: Actions taken (promoting a job, deleting a card, moving cards between stages) are synced globally across all 3 variants so you can judge how the same state feels in each design.
- **Responsive Theme**: Styled using modern glassmorphism (radial grid mesh, dark slate backgrounds, backdrop-filter blurs, neon accent glows).

---

## Next Steps
1. The user will run the prototype, click through the variants, and evaluate the layouts.
2. Once a design or hybrid layout (e.g., the Kanban board for tracking paired with the Split Feed for reading details) is chosen, document it in an ADR or in the final migration roadmap, delete the prototype files (`prototype_dashboard.py`, `prototype_dashboard.html`), and begin implementing the production FastAPI service under the new `src/` folder structure.
