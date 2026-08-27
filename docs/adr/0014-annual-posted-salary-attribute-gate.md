# 0014: Annual Posted Salary attribute gate — annualMax and currency-agnostic Min

## Status

Accepted.

## Context

Posted Salary on listings arrives as messy free text (hourly vs yearly, multi-location bands, mixed currencies). We normalize at Resume Matcher writeback into an **Annual Posted Salary** band and apply **Salary Min** from Job Search Settings as a post-evaluation attribute gate (same family as remote type / seniority / Employment Type). Two gate details are easy to “fix” later without this note.

## Decision

1. **Gate on `annualMax`, not `annualMin` or midpoint** — A job passes Salary Min when the top of its annual band is at least the minimum. A band that reaches the floor (e.g. `100k–130k` vs Min `120k`) stays eligible; requiring the bottom of the band above Min would reject roles whose range still includes acceptable pay.

2. **No FX and no currency switcher in v1** — Store the band in the listing’s native currency. Salary Min compares bare annual numbers across currencies (CAD 120000 and USD 120000 are equal for the threshold). Unknown / missing Posted Salary passes the salary gate. Currency conversion and a native-currency filter remain future options.

## Considered Options

- **Gate on `annualMin` or midpoint** — Rejected; too aggressive for overlapping bands.
- **Board Controls Salary Min / FX display conversion** — Rejected for v1; Min stays in Job Search Settings and applies only after matcher writeback.
- **Native-currency filter (show CAD only, etc.)** — Rejected for v1 in favor of currency-agnostic compare; revisit if mixed-currency boards become confusing.
