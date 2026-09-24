from src.descriptions.matching.model_matcher import (
    get_model_match_keys,
)


def test_exact_model_is_first():
    assert get_model_match_keys("GENESIS E-315W") == (
        "GENESIS E-315W",
        "GENESIS E-315",
    )


def test_genesis_e_415w_has_fallback():
    assert get_model_match_keys("GENESIS E-415W") == (
        "GENESIS E-415W",
        "GENESIS E-415",
    )


def test_genesis_ep_335w_has_fallback():
    assert get_model_match_keys("GENESIS EP-335W") == (
        "GENESIS EP-335W",
        "GENESIS EP-335",
    )


def test_genesis_ep_435w_has_fallback():
    assert get_model_match_keys("GENESIS EP-435W") == (
        "GENESIS EP-435W",
        "GENESIS EP-435",
    )


def test_genesis_epx_335w_has_fallback():
    assert get_model_match_keys("GENESIS EPX-335W") == (
        "GENESIS EPX-335W",
        "GENESIS EPX-335",
    )


def test_genesis_epx_435w_has_fallback():
    assert get_model_match_keys("GENESIS EPX-435W") == (
        "GENESIS EPX-435W",
        "GENESIS EPX-435",
    )


def test_exact_genesis_model_has_no_fallback():
    assert get_model_match_keys("GENESIS E-315") == (
        "GENESIS E-315",
    )


def test_wr_suffix_is_not_removed():
    assert get_model_match_keys("GENESIS E-330WR") == (
        "GENESIS E-330WR",
    )


def test_non_genesis_w_model_is_not_modified():
    assert get_model_match_keys("SPIRIT E-315W") == (
        "SPIRIT E-315W",
    )


def test_empty_model_returns_empty_tuple():
    assert get_model_match_keys("") == ()
def test_q3200n_plus_can_fall_back_to_q3200n():
    assert get_model_match_keys("Q3200N+") == (
        "Q3200N+",
        "Q3200N",
    )


def test_q2800n_plus_does_not_use_q3200_fallback():
    assert get_model_match_keys("Q2800N+") == (
        "Q2800N+",
    )