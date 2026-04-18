"""Unit tests for safety blacklist matcher (T E.1)."""

from __future__ import annotations

from autovisiontest.safety.blacklist import (
    click_hits_blacklist,
    key_combo_hits_blacklist,
    type_hits_blacklist,
)


# ── click_hits_blacklist ─────────────────────────────────────────────────


class TestClickHitsBlacklist:
    def test_click_delete_button_hit(self) -> None:
        hit, keyword = click_hits_blacklist(["删除"])
        assert hit is True
        assert keyword == "删除"

    def test_click_english_delete_hit(self) -> None:
        hit, keyword = click_hits_blacklist(["Delete"])
        assert hit is True
        assert keyword == "Delete"

    def test_click_embedded_keyword_hit(self) -> None:
        """Keyword embedded in longer text should still match."""
        hit, keyword = click_hits_blacklist(["永久删除文件"])
        assert hit is True
        # "删除" appears earlier in CLICK_KEYWORDS and matches first
        assert keyword in {"删除", "永久删除"}

    def test_click_safe_button_miss(self) -> None:
        hit, keyword = click_hits_blacklist(["保存", "确定"])
        assert hit is False
        assert keyword is None

    def test_click_empty_list_miss(self) -> None:
        hit, keyword = click_hits_blacklist([])
        assert hit is False
        assert keyword is None

    def test_click_case_insensitive(self) -> None:
        hit, keyword = click_hits_blacklist(["format"])
        assert hit is True
        assert keyword == "Format"


# ── type_hits_blacklist ──────────────────────────────────────────────────


class TestTypeHitsBlacklist:
    def test_type_rm_rf_hit(self) -> None:
        hit, pattern = type_hits_blacklist("rm -rf /")
        assert hit is True
        assert pattern == r"\brm\s+-rf"

    def test_type_del_s_hit(self) -> None:
        hit, pattern = type_hits_blacklist("del /s C:\\stuff")
        assert hit is True
        assert pattern == r"\bdel\s+/[sq]"

    def test_type_format_drive_hit(self) -> None:
        hit, pattern = type_hits_blacklist("format c:")
        assert hit is True
        assert pattern == r"\bformat\s+[a-z]:"

    def test_type_normal_text_miss(self) -> None:
        hit, pattern = type_hits_blacklist("hello world")
        assert hit is False
        assert pattern is None

    def test_type_empty_string_miss(self) -> None:
        hit, pattern = type_hits_blacklist("")
        assert hit is False
        assert pattern is None

    def test_type_case_insensitive(self) -> None:
        hit, pattern = type_hits_blacklist("RM -RF /")
        assert hit is True
        assert pattern == r"\brm\s+-rf"


# ── key_combo_hits_blacklist ─────────────────────────────────────────────


class TestKeyComboHitsBlacklist:
    def test_alt_f4_hit(self) -> None:
        hit, combo = key_combo_hits_blacklist(("alt", "f4"))
        assert hit is True
        assert combo == "alt+f4"

    def test_ctrl_shift_del_hit(self) -> None:
        hit, combo = key_combo_hits_blacklist(("ctrl", "shift", "del"))
        assert hit is True
        assert combo == "ctrl+del+shift"

    def test_win_l_hit(self) -> None:
        hit, combo = key_combo_hits_blacklist(("win", "l"))
        assert hit is True
        assert combo == "l+win"

    def test_safe_combo_miss(self) -> None:
        hit, combo = key_combo_hits_blacklist(("ctrl", "s"))
        assert hit is False
        assert combo is None

    def test_case_insensitive(self) -> None:
        hit, combo = key_combo_hits_blacklist(("Alt", "F4"))
        assert hit is True
        assert combo == "alt+f4"

    def test_order_insensitive(self) -> None:
        hit, combo = key_combo_hits_blacklist(("f4", "alt"))
        assert hit is True
        assert combo == "alt+f4"

    def test_empty_tuple_miss(self) -> None:
        hit, combo = key_combo_hits_blacklist(())
        assert hit is False
        assert combo is None
