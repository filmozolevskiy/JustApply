import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kanban_js import load_kanban_js, read_dashboard_html, read_task_log_client


def test_dashboard_html_marks_page_unload_before_sse_error_handling():
    content = read_dashboard_html()
    task_log = read_task_log_client()
    assert "pageUnloading" in task_log
    assert "function markPageUnloading()" in task_log
    assert "window.addEventListener('beforeunload', markPageUnloading)" in content
    assert "window.addEventListener('pagehide'" in content


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
    content = read_dashboard_html()
    assert "function restoreActiveScrapeTask()" in content
    assert "Reconnecting to active background task" in content
    assert "loadJobs().then(() => {" in content
    assert "restoreActiveScrapeTask();" in content


def test_dashboard_html_restore_active_reclassify_task_after_load():
    content = read_dashboard_html()
    assert "function restoreActiveReclassifyTasks()" in content
    assert "Reconnecting to" in content
    assert "active re-classify task" in content
    assert "restoreActiveReclassifyTasks();" in content
    assert "ACTIVE_RECLASSIFY_TASKS_KEY" in content


def test_dashboard_html_scrape_warning_only_for_unexpected_disconnect():
    content = read_dashboard_html()
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
