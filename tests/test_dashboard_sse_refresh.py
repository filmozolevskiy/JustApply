import os


def _read_dashboard_html():
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "web", "dashboard.html")
    with open(html_path) as f:
        return f.read()


def test_dashboard_html_marks_page_unload_before_sse_error_handling():
    content = _read_dashboard_html()
    assert "let pageUnloading = false" in content
    assert "function markPageUnloading()" in content
    assert "window.addEventListener('beforeunload', markPageUnloading)" in content
    assert "window.addEventListener('pagehide'" in content


def test_dashboard_html_sse_error_skips_cleanup_on_intentional_close():
    content = _read_dashboard_html()
    connect_start = content.find("function connectTaskLogStream(")
    assert connect_start != -1, "connectTaskLogStream function not found"
    connect_body = content[connect_start:connect_start + 2200]
    assert "_intentionalClose" in connect_body
    assert "pageUnloading" in connect_body
    assert "function closeTaskLogStreamQuietly(" in content
    assert "if (intentional)" in connect_body


def test_dashboard_html_restore_active_scrape_task_after_load():
    content = _read_dashboard_html()
    assert "function restoreActiveScrapeTask()" in content
    assert "Reconnecting to active background task" in content
    assert "loadJobs().then(() => {" in content
    assert "restoreActiveScrapeTask();" in content


def test_dashboard_html_scrape_warning_only_for_unexpected_disconnect():
    content = _read_dashboard_html()
    assert "Scraper SSE stream closed unexpectedly." in content
    connect_start = content.find(".then(data => {\n        const taskId = data.task_id;")
    assert connect_start != -1, "scrape SSE connect block not found"
    scrape_sse_block = content[connect_start:connect_start + 1800]
    assert "Scraper SSE stream closed unexpectedly." in scrape_sse_block
    restore_start = content.find("function restoreActiveScrapeTask(")
    assert restore_start != -1
    restore_end = content.find("function restoreActiveEnrichTask(", restore_start)
    restore_body = content[restore_start:restore_end]
    assert "Scraper SSE stream closed unexpectedly." not in restore_body
    assert "Background scrape task is no longer available on the server." in restore_body
