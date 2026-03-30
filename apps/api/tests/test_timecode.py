from app.utils.timecode import ms_to_timecode


def test_ms_to_timecode():
    assert ms_to_timecode(3_723_045) == "01:02:03.045"


def test_zero_milliseconds():
    assert ms_to_timecode(0) == "00:00:00.000"


def test_negative_milliseconds():
    import pytest
    with pytest.raises(ValueError):
        ms_to_timecode(-1)


def test_large_value_over_one_hour():
    assert ms_to_timecode(7_265_432) == "02:01:05.432"
