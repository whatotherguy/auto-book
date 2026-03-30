from app.utils.timecode import ms_to_timecode


def test_ms_to_timecode():
    assert ms_to_timecode(3_723_045) == "01:02:03.045"


def test_zero_milliseconds():
    assert ms_to_timecode(0) == "00:00:00.000"


def test_negative_milliseconds():
    try:
        result = ms_to_timecode(-1)
    except ValueError:
        return

    assert result == "-1:59:59.999"


def test_large_value_over_one_hour():
    assert ms_to_timecode(7_265_432) == "02:01:05.432"
