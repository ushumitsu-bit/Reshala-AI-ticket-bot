from utils.support_common import esc


def test_esc_html_special_chars():
    assert esc("<b>&") == "&lt;b&gt;&amp;"


def test_esc_none():
    assert esc(None) == ""


def test_esc_non_string():
    assert esc(123) == "123"


def test_esc_preserves_cyrillic():
    assert esc("Привет") == "Привет"
