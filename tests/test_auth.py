from datetime import timedelta

from auth import (
    SESSION_DURATION,
    derive_track_name,
    generate_session_token,
    hash_password,
    verify_password,
)


def test_hash_password_produces_a_verifiable_but_different_string():
    password = "correct horse battery staple"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("the-real-password")
    assert verify_password("a-wrong-guess", hashed) is False


def test_hash_password_is_salted_so_two_hashes_of_the_same_password_differ():
    hashed_a = hash_password("same-password")
    hashed_b = hash_password("same-password")
    assert hashed_a != hashed_b
    assert verify_password("same-password", hashed_a) is True
    assert verify_password("same-password", hashed_b) is True


def test_generate_session_token_produces_unique_url_safe_strings():
    tokens = {generate_session_token() for _ in range(20)}
    assert len(tokens) == 20
    for token in tokens:
        assert len(token) >= 32
        assert " " not in token


def test_session_duration_is_thirty_days():
    assert SESSION_DURATION == timedelta(days=30)


def test_derive_track_name_returns_short_goal_text_unchanged():
    assert derive_track_name("Learn RAG") == "Learn RAG"


def test_derive_track_name_truncates_long_goal_text_at_a_word_boundary():
    goal = "I want to understand how RAG differs from just stuffing context into a giant prompt window"
    name = derive_track_name(goal, max_length=30)

    assert len(name) <= 31  # 30 chars + the ellipsis character
    assert name.endswith("…")
    assert not name[:-1].endswith(" ")  # trimmed back to the last full word, no trailing space before the ellipsis
    assert goal.startswith(name[:-1])


def test_derive_track_name_falls_back_to_hard_truncation_when_no_word_boundary_exists():
    # A leading space right at the truncation point makes rsplit(" ", 1)[0] empty;
    # without a fallback this would collapse to just "…".
    goal = " " + "x" * 80
    name = derive_track_name(goal)

    assert name != "…"
    assert name == goal[:60] + "…"
