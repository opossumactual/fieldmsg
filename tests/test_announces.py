import time
from fieldmsg.announces import format_announce, relative_time


def test_format_with_display_name():
    t = time.time()
    result = format_announce("aabbccdd11223344", "Alice", 2, t, "LoRa")
    assert "Alice" in result
    assert "aabbccdd1122" in result
    assert "2 hops" in result
    assert "LoRa" in result


def test_format_without_display_name():
    t = time.time()
    result = format_announce("aabbccdd11223344", None, 1, t, None)
    assert "aabbccdd112233" in result  # first 16 chars of hash
    assert "1 hop" in result
    assert "hops" not in result  # singular


def testrelative_time_just_now():
    assert relative_time(time.time()) == "just now"


def testrelative_time_minutes():
    assert relative_time(time.time() - 120) == "2m ago"


def testrelative_time_hours():
    assert relative_time(time.time() - 7200) == "2h ago"


def testrelative_time_days():
    assert relative_time(time.time() - 172800) == "2d ago"
