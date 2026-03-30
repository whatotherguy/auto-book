from app.services.text_normalize import normalize_for_alignment, normalize_text


def test_normalize_text_basic():
    assert normalize_text("Hello-World!") == "hello world"


def test_normalize_text_numbers():
    assert normalize_text("Chapter 1") == "chapter 1"


def test_normalize_text_punctuation():
    assert normalize_text("Hello, world!!!") == "hello world"


def test_normalize_text_mixed_case():
    assert normalize_text("MiXeD CaSe") == "mixed case"


def test_normalize_text_multiple_spaces():
    assert normalize_text("alpha   beta\tgamma") == "alpha beta gamma"


def test_normalize_text_unicode_accented_characters():
    assert normalize_text("caf\u00e9 d\u00e9j\u00e0 vu") == "caf d j vu"


def test_normalize_for_alignment_expands_common_abbreviations():
    assert normalize_for_alignment("Dr. Mr. Mrs. Ms. St. Jr. Sr. Prof.") == "doctor mister missus miss saint junior senior professor"


def test_normalize_for_alignment_handles_currency_commas_and_ordinals():
    assert normalize_for_alignment("$1,200 £50 1st 2nd 3rd 4th 20th 21st") == "1200 50 first second third fourth twentieth 21"


def test_normalize_for_alignment_removes_am_pm_period_variants():
    assert normalize_for_alignment("10 a.m. and 3 p.m.") == "10 am and 3 pm"
