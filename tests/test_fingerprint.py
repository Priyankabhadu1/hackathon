from src.fingerprint import diff, fingerprint, is_empty


def test_values_do_not_move_the_fingerprint():
    cheap = {"data": [{"price": {"total": "100.00", "currency": "EUR"}}]}
    dear = {"data": [{"price": {"total": "982.45", "currency": "EUR"}}]}
    assert fingerprint(cheap)["hash"] == fingerprint(dear)["hash"]


def test_array_length_does_not_move_the_fingerprint():
    one = {"data": [{"id": "1"}]}
    many = {"data": [{"id": "1"}, {"id": "2"}, {"id": "3"}]}
    assert fingerprint(one)["hash"] == fingerprint(many)["hash"]


def test_rename_is_visible_as_one_add_and_one_remove():
    before = fingerprint({"data": [{"price": {"total": "1.00"}}]})
    after = fingerprint({"data": [{"price": {"grandTotal": "1.00"}}]})
    delta = diff(before, after)
    assert delta["added"] == ["data[].price.grandTotal"]
    assert delta["removed"] == ["data[].price.total"]


def test_retype_is_reported():
    before = fingerprint({"seats": 4})
    after = fingerprint({"seats": "4"})
    assert diff(before, after)["retyped"][0]["path"] == "seats"


def test_identical_payload_has_no_delta():
    payload = {"data": [{"price": {"total": "1.00", "currency": "EUR"}}]}
    assert is_empty(diff(fingerprint(payload), fingerprint(payload)))
