"""classify.py: PR URL extraction + status classification."""

from __future__ import annotations

import pytest

from classify import classify, extract_pr_url


# --- extract_pr_url --------------------------------------------------------

def test_extract_pr_url_basic():
    text = "Created PR: https://github.com/owner/repo/pull/42"
    assert extract_pr_url(text) == "https://github.com/owner/repo/pull/42"


def test_extract_pr_url_in_log_format():
    text = """
    Some log noise
    gh pr create --title ... yielded: https://github.com/xslkim/AutoAgent/pull/99
    More noise
    """
    assert "pull/99" in extract_pr_url(text)


def test_extract_pr_url_no_match_returns_none():
    assert extract_pr_url("nothing here") is None


# --- classify --------------------------------------------------------------

def test_clean_exit_with_pr_url_is_awaiting_ci():
    v = classify(0, "Pushed branch. PR: https://github.com/a/b/pull/1", "")
    assert v.status == "awaiting_ci"
    assert v.pr_url is not None


def test_clean_exit_without_pr_url_is_success():
    v = classify(0, "Done.", "")
    assert v.status == "success"
    assert v.pr_url is None


def test_non_zero_exit_is_failed():
    v = classify(1, "", "something went wrong")
    assert v.status == "failed"


def test_path_violation_error_code_routes_to_needs_human():
    v = classify(1, "", "MCP error -32030 PathViolation: tried to write .unity")
    assert v.status == "needs_human"
    assert "path" in v.reason.lower()


def test_path_violation_chinese_text_routes_to_needs_human():
    v = classify(1, "", "路径白名单违规 — 你不能修改 fixtures/")
    assert v.status == "needs_human"


def test_visual_property_write_routes_to_needs_human():
    v = classify(1, "", "Error code -32003 VisualPropertyWrite")
    assert v.status == "needs_human"
    assert "visual" in v.reason.lower()


def test_auth_failure_routes_to_needs_human():
    v = classify(1, "", "HTTP 401 Unauthorized")
    assert v.status == "needs_human"
    assert "auth" in v.reason.lower()


def test_missing_api_key_routes_to_needs_human():
    v = classify(1, "", "ANTHROPIC_API_KEY not set")
    assert v.status == "needs_human"


def test_missing_deepseek_key_routes_to_needs_human():
    v = classify(1, "", "DEEPSEEK_API_KEY not set")
    assert v.status == "needs_human"


def test_provider_not_configured_routes_to_needs_human():
    v = classify(1, "", "No provider found for model deepseek/deepseek-v4-pro")
    assert v.status == "needs_human"


def test_policy_violation_beats_clean_exit():
    """Even if claude returns 0, a policy violation in stderr should fail safe."""
    v = classify(0, "PR: https://github.com/a/b/pull/1", "PathViolation flagged")
    assert v.status == "needs_human"


def test_path_whitelist_filename_is_not_a_violation():
    """An agent log that merely *reads* `path_whitelist.yml` must not be
    misclassified as a path violation — only the real error phrasing counts.
    Regression: classify.py used to match the bare word 'whitelist'.
    """
    stdout = (
        "Read scripts\\ci\\path_whitelist.yml\n"
        "Created PR: https://github.com/xslkim/AutoAgent/pull/64\n"
    )
    v = classify(0, stdout, "")
    assert v.status == "awaiting_ci"
    assert "pull/64" in v.pr_url
