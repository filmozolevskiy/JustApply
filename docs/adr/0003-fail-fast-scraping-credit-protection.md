# 0003: Fail-Fast Web Scraping and API Credit Protection

## Status

Accepted

## Context

Our hybrid scraping architecture triggers dataset snapshot runs on third-party commercial APIs (specifically Bright Data and Apify). Sourcing job listings and outreach contacts triggers background crawler runs which consume paid API credits. 

Previously, the error handler inside `scrape_linkedin_jobs` attempted to recursively call itself in fallback mode when the primary API request failed. However, if the API failure was persistent (e.g., due to an expired API key, network timeout, or credit exhaustion), this recursive callback logic led to an infinite loop, repeatedly triggering triggers/discovery jobs and draining the user's credits.

We need a design that guarantees no runaway execution loops can trigger paid API requests.

## Decision

We decide to apply the following architectural constraints to the web scraping integrations:

1. **Separation of Modes**: Split the mock/simulation logic from the real API logic into separate, private helper functions: `_scrape_linkedin_jobs_mock()` and `_scrape_linkedin_jobs_real()`.
2. **Fail-Fast Error Handling**: Remove silent mock fallbacks. If the real scraping engine fails, it must raise the exception and propagate it up immediately.
3. **No Retry on Paid Operations**: Do not retry trigger requests (which start snapshot crawler tasks and consume credits) automatically. If the trigger request fails, it fails immediately.
4. **Strict Ban on Recursion**: Ban any self-referencing recursive calls in error handling.
5. **Finite Loop-Based Polling Retries**: Subsequent non-paid operations (such as polling progress or fetching snapshot results) may be retried up to 3 times using an explicit `for` loop with exponential backoff.
6. **Trigger Rate Limiting**: Store trigger timestamps in memory and reject consecutive real scraping triggers if requested within 60 seconds of a previous trigger.

## Consequences

* **Transparency**: API failures, authentication errors, and credit depletion will be immediately visible in the task log panel and CLI output, rather than being masked by silent mock data.
* **Credit Security**: Runaway code loops cannot trigger paid external dataset crawlers, preventing catastrophic credit drain scenarios.
* **Mock Isolation**: Running the application in offline mock mode must be explicitly configured (`MOCK_SCRAPER=true`), preventing developer confusion between simulated and production data.
