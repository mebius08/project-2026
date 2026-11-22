from prices import apply_discount


def test_ten_percent_off():
    assert apply_discount(200, 10) == 180


def test_no_discount():
    assert apply_discount(200, 0) == 200
