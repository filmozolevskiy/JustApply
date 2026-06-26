# ADR 0003: Parallel Batch Evaluation for Search Pipeline

## Status
Superseded by ADR 0010 (Gemini Batch API for Job Evaluation). The "Prompt Packing" strategy described below (15 jobs per prompt, up to 30 parallel live HTTP calls) has been replaced by an asynchronous Batch Evaluation Job. Retained for historical context.

## Context
The job search pipeline was previously evaluating jobs sequentially (one-by-one). As the number of scraped jobs increased (often 100-500+ per search), the evaluation phase became a significant bottleneck, taking several minutes to complete. 

The system uses Gemini 1.5 Flash, which has a large context window and high rate limits for Tier 1 users (1,000 RPM / 1M TPM).

## Decision
We implemented parallel batch evaluation in the `Search & Evaluation Pipeline`.

1.  **Prompt Batching**: Group 15 jobs into a single LLM prompt. This reduces network round-trips and stays well within the 1M TPM limit.
2.  **Parallel Execution**: Run up to 30 batch requests in parallel using `asyncio.Semaphore`. This allows processing up to 450 jobs simultaneously.
3.  **Deduplication First**: Deduplicate jobs against the database *before* evaluation to avoid wasting tokens on existing listings.
4.  **Robust Fallback**: If a batch evaluation fails (invalid JSON or count mismatch), the system falls back to sequential evaluation for only the jobs in that specific batch.

## Consequences
- **Speed**: Evaluation time for 500 jobs reduced from ~5-10 minutes to ~20-30 seconds.
- **Cost**: Fewer individual API calls; better utilization of the context window.
- **Complexity**: Added logic for chunking, parallel semaphores, and fallback error handling.
- **Rate Limits**: The current configuration (30 parallel batches of 15) is optimized for Tier 1 limits. Users on the Free Tier (10 RPM) may trigger 429 errors unless `MAX_CONCURRENCY` is reduced.
