from src.descriptions.matching.model_candidate_selector import (
    select_model_candidates,
)


def test_q3200n_plus_falls_back_to_q3200n_grill():
    products = [
        {
            "sku": "3400854",
            "name": "Q3200N+ COVER EMEA",
            "categories": [
                {"id": 422, "name": "Gāzes grili"},
                {"id": 458, "name": "Pārvalki"},
                {"id": 247, "name": "Weber gāzes grili"},
            ],
        },
        {
            "sku": "1501137",
            "name": "Gāzes grils Weber Q3200N",
            "categories": [
                {"id": 422, "name": "Gāzes grili"},
                {"id": 247, "name": "Weber gāzes grili"},
            ],
        },
    ]

    matches = select_model_candidates(
        "Q3200N+",
        products,
    )

    assert [product["sku"] for product in matches] == [
        "1501137",
    ]
def test_exact_model_match_has_priority_over_fallback():
    products = [
        {
            "sku": "EXACT",
            "name": "Gāzes grils Genesis E-315W",
            "categories": [
                {"id": 422, "name": "Gāzes grili"},
                {"id": 247, "name": "Weber gāzes grili"},
            ],
        },
        {
            "sku": "FALLBACK",
            "name": "Gāzes grils Genesis E-315",
            "categories": [
                {"id": 422, "name": "Gāzes grili"},
                {"id": 247, "name": "Weber gāzes grili"},
            ],
        },
    ]

    matches = select_model_candidates(
        "GENESIS E-315W",
        products,
    )

    assert [product["sku"] for product in matches] == [
        "EXACT",
    ]
def test_genesis_w_uses_fallback_when_exact_model_is_missing():
    products = [
        {
            "sku": "1501079",
            "name": "Gāzes grils Genesis E-315",
            "categories": [
                {"id": 422, "name": "Gāzes grili"},
                {"id": 247, "name": "Weber gāzes grili"},
            ],
        },
    ]

    matches = select_model_candidates(
        "GENESIS E-315W",
        products,
    )

    assert [product["sku"] for product in matches] == [
        "1501079",
    ]