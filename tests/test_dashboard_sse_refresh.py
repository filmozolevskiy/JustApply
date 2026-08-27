
from kanban_js import load_dashboard_js, load_kanban_js, read_task_log_client


def test_dashboard_html_marks_page_unload_before_sse_error_handling():
    task_log = read_task_log_client()
    dashboard_js = load_dashboard_js()
    assert "pageUnloading" in task_log
    assert "function markPageUnloading()" in task_log
    assert "window.addEventListener('beforeunload', markPageUnloading)" in dashboard_js
    assert "window.addEventListener('pagehide'" in dashboard_js


def test_dashboard_starts_batch_poller_log_stream():
    """Dashboard bootstrap opens always-on batch-poller SSE via taskLogClient."""
    task_log = read_task_log_client()
    dashboard_js = load_dashboard_js()
    assert "function connectBatchPollerLogStream(" in task_log
    assert "/api/batch-poller/logs?skip=" in task_log
    assert "BATCH_POLLER_LOG_SKIP_KEY" in task_log
    assert "handleTaskLogMessage(logData," in task_log
    assert "onBoardNeedsRefresh" in task_log
    assert "connectBatchPollerLogStream({" in dashboard_js
    assert "refreshBoardQuietly" in dashboard_js
    assert "getBatchPollerEventSource()" in dashboard_js
    # Enrichment stays on per-task /api/logs streams, not the poller endpoint.
    assert task_log.count("new EventSource(`/api/batch-poller/logs") == 1
    assert "new EventSource(`/api/logs/${taskId}?skip=${skip}`)" in task_log


def test_dashboard_refreshes_board_after_search_and_evaluation():
    """Search done + evaluation settled/summary paths reload the board without a page refresh."""
    content = load_dashboard_js()
    assert "refreshBoardQuietly" in content
    assert "onEvaluationSettled" in content
    assert "onBoardNeedsRefresh" in content
    assert "BOARD_REFRESH_WHILE_ASSESSING_MS" in content
    # Scrape completion reloads the board so Scraped cards appear even if SSE results were missed.
    scrape_done_idx = content.find("Scraper process complete.")
    assert scrape_done_idx != -1
    scrape_done_window = content[scrape_done_idx : scrape_done_idx + 350]
    assert "refreshBoardQuietly" in scrape_done_window
    # Quiet reload must not spam Task Logs with "Loaded N jobs" on every chunk.
    assert "loadJobs({ quiet: true })" in content or "loadJobs({ quiet: true }" in content
    assert "function loadJobs({ quiet = false }" in content


def test_dashboard_html_sse_error_skips_cleanup_on_intentional_close():
    content = load_kanban_js()
    connect_start = content.find("function connectTaskLogStream(")
    assert connect_start != -1, "connectTaskLogStream function not found"
    connect_body = content[connect_start:connect_start + 2200]
    assert "_intentionalClose" in connect_body
    assert "pageUnloading" in connect_body
    assert "function closeTaskLogStreamQuietly(" in content
    assert "if (intentional)" in connect_body

def test_dashboard_html_restore_active_scrape_task_after_load():
    content = load_dashboard_js()
    assert "function restoreActiveScrapeTask()" in content
    assert "Reconnecting to active background task" in content
    assert "board.loadJobs().then(() => {" in content
    assert "restoreActiveScrapeTask();" in content

def test_dashboard_html_restore_active_reclassify_task_after_load():
    content = load_dashboard_js()
    assert "function restoreActiveReclassifyTasks()" in content
    assert "Reconnecting to" in content
    assert "active re-classify task" in content
    assert "restoreActiveReclassifyTasks();" in content
    assert "ACTIVE_RECLASSIFY_TASKS_KEY" in content

def test_dashboard_html_scrape_warning_only_for_unexpected_disconnect():
    content = load_dashboard_js()
    assert "Scraper SSE stream closed unexpectedly." in content
    connect_start = content.find("const taskId = data.task_id;")
    assert connect_start != -1, "scrape SSE connect block not found"
    scrape_sse_block = content[connect_start:connect_start + 2200]
    assert "Scraper SSE stream closed unexpectedly." in scrape_sse_block
    assert "clearStorageOnError: false" in scrape_sse_block
    assert "reconnect" in scrape_sse_block.lower() or "Reconnecting" in scrape_sse_block
    restore_start = content.find("function restoreActiveScrapeTask(")
    assert restore_start != -1
    restore_end = content.find("function restoreActiveEnrichTask(", restore_start)
    restore_body = content[restore_start:restore_end]
    assert "Scraper SSE stream closed unexpectedly." not in restore_body
    assert "Background scrape task is no longer available on the server." in restore_body


def test_task_log_client_optional_preserve_storage_on_error():
    task_log = read_task_log_client()
    assert "clearStorageOnError" in task_log
    connect_start = task_log.find("function connectTaskLogStream(")
    assert connect_start != -1
    connect_body = task_log[connect_start : connect_start + 2800]
    assert "clearStorageOnError" in connect_body
    assert "localStorage.removeItem(taskKey)" in connect_body
    assert "if (clearStorageOnError)" in connect_body