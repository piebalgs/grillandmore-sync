import pytest

from src.descriptions.matching.model_extractor import (
    extract_model,
    extract_model_from_texts,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Weber® Q 1100N Gas Grill",
            "Q1100N",
        ),
        (
            "Gāzes grils Weber Q1100N",
            "Q1100N",
        ),
        (
            "Weber® Q 1200N w/stand Gas Grill",
            "Q1200N",
        ),
        (
            "Gāzes grils Weber Q1200N ar statīvu",
            "Q1200N",
        ),
        (
            "Weber Q 2200N w/stand Gas Grill",
            "Q2200N",
        ),
        (
            "Gāzes grils Weber Q2200N ar Premium statīvu",
            "Q2200N",
        ),
        (
            "Weber® Q 2800N+ Gas Grill with Premium Cart",
            "Q2800N+",
        ),
        (
            "Gāzes grils Weber Q2800N+ ar Premium statīvu",
            "Q2800N+",
        ),
        (
            "Spirit® E-325 Gas Grill",
            "SPIRIT E-325",
        ),
        (
            "Gāzes grils Spirit EP-325",
            "SPIRIT EP-325",
        ),
        (
            "Spirit® EX-325 Smart Gas Grill",
            "SPIRIT EX-325",
        ),
        (
            "Spirit® EPX-435 Smart Gas Grill",
            "SPIRIT EPX-435",
        ),
        (
            "Genesis® E-435 Gas Grill",
            "GENESIS E-435",
        ),
        (
            "Gāzes grils Genesis E435",
            "GENESIS E-435",
        ),
        (
            "Genesis® EX-425W W Gas Grill",
            "GENESIS EX-425W",
        ),
        (
            "Gāzes grils GENESIS EX-425W LP BLK 75CP",
            "GENESIS EX-425W",
        ),
        (
            "Summit FS38 E Gas Grill",
            "SUMMIT FS38 E",
        ),
        (
            "Summit FS38X E Gas Grill",
            "SUMMIT FS38X E",
        ),
        (
            "Summit FS38 S Gas Grill",
            "SUMMIT FS38 S",
        ),
        (
            "Summit FS38X S Gas Grill",
            "SUMMIT FS38X S",
        ),
    ],
)
def test_extract_model(text, expected):
    assert extract_model(text) == expected


def test_extract_model_returns_empty_string_for_unknown_product():
    assert extract_model("Premium Barbecue Cover") == ""


def test_extract_model_returns_empty_string_for_empty_text():
    assert extract_model("") == ""


def test_extract_model_from_texts_uses_first_detected_model():
    assert (
        extract_model_from_texts(
            "No model here",
            "Weber Q 1200N w/stand Gas Grill",
            "Spirit E-325",
        )
        == "Q1200N"
    )


def test_extract_model_from_texts_can_use_description():
    assert (
        extract_model_from_texts(
            "Weber Q 2800N w/cart Gas Grill",
            "Experience new possibilities with the Q2800N+ Gas Grill.",
        )
        == "Q2800N+"
    )
def test_extract_model_from_texts_prefers_plus_variant_of_same_model():
    assert (
        extract_model_from_texts(
            "Weber Q 2800N w/cart Gas Grill",
            "Experience new possibilities with the Q2800N+ Gas Grill.",
        )
        == "Q2800N+"
    )


def test_extract_model_from_texts_does_not_replace_different_model():
    assert (
        extract_model_from_texts(
            "Weber Q 1200N Gas Grill",
            "Accessory also compatible with Weber Q2200N.",
        )
        == "Q1200N"
    )

def test_extract_model_from_texts_prefers_more_precise_q_variant():
    assert (
        extract_model_from_texts(
            "Weber Q 3200 w/cart Gas Grill",
            (
                "Enjoy the ultimate backyard grilling experience "
                "with the powerful Q3200N+ Gas Grill with Premium Cart."
            ),
        )
        == "Q3200N+"
    )
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Weber Traveler® Compact Gas Grill",
            "TRAVELER COMPACT",
        ),
        (
            "Weber Traveler® Gas Grill",
            "TRAVELER",
        ),
        (
            "Go-Anywhere Gas Grill",
            "GO-ANYWHERE",
        ),
    ],
)
def test_extract_named_portable_models(text, expected):
    assert extract_model(text) == expected