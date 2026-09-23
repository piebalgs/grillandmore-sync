from src.descriptions.matching.product_filter import (
    is_grill_candidate,
)


def test_regular_gas_grill_is_candidate():
    product = {
        "sku": "1501137",
        "name": "Gāzes grils Weber Q3200N",
        "categories": [
            {
                "id": 422,
                "name": "Gāzes grili",
                "slug": "gazes-grili",
            },
            {
                "id": 247,
                "name": "Weber gāzes grili",
                "slug": "weber-gazes-grili",
            },
        ],
    }

    assert is_grill_candidate(product) is True


def test_cover_is_not_grill_candidate():
    product = {
        "sku": "3400854",
        "name": "Q3200N+ COVER EMEA",
        "categories": [
            {
                "id": 422,
                "name": "Gāzes grili",
                "slug": "gazes-grili",
            },
            {
                "id": 458,
                "name": "Pārvalki",
                "slug": "parvalki",
            },
            {
                "id": 247,
                "name": "Weber gāzes grili",
                "slug": "weber-gazes-grili",
            },
        ],
    }

    assert is_grill_candidate(product) is False


def test_latvian_cover_is_not_grill_candidate():
    product = {
        "sku": "7118",
        "name": "Premium pārvalks Q 2000 sērijas griliem",
        "categories": [
            {
                "id": 422,
                "name": "Gāzes grili",
                "slug": "gazes-grili",
            },
            {
                "id": 458,
                "name": "Pārvalki",
                "slug": "parvalki",
            },
            {
                "id": 247,
                "name": "Weber gāzes grili",
                "slug": "weber-gazes-grili",
            },
        ],
    }

    assert is_grill_candidate(product) is False