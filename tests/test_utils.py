import string

from app.utils import generate_track_number, normalize_track_number


def test_generate_track_number_length_and_alphabet():
    track = generate_track_number()
    assert len(track) == 16
    assert set(track) <= set(string.ascii_uppercase + string.digits)


def test_generate_track_number_is_effectively_unique():
    tracks = {generate_track_number() for _ in range(500)}
    assert len(tracks) == 500


def test_normalize_track_number_strips_and_uppercases():
    assert normalize_track_number("  ab12cd34ef56gh78  ") == "AB12CD34EF56GH78"


def test_normalize_track_number_handles_empty_and_none():
    assert normalize_track_number("") == ""
    assert normalize_track_number(None) == ""
