from app.utils.tokenization import tokenize


def test_tokenize():
    assert tokenize("one two  three") == ["one", "two", "three"]
