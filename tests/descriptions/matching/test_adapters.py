import pytest

from src.descriptions.matching.adapters import (
    description_product_from_weber,
    supplier_product_from_woocommerce,
)
from src.descriptions.parser import ProductDescription


def test_description_product_from_weber():
    source = ProductDescription(
        sku="WEBERQ_1100N_BL",
        import_id="WEBER_Q_1100N",
        title="Weber® Q 1100N Gas Grill",
        title_line_1="Weber® Q 1100N",
    )

    result = description_product_from_weber(source)

    assert result.description_key == "WEBER_Q_1100N"
    assert result.title == "Weber® Q 1100N Gas Grill"
    assert result.title_line_1 == "Weber® Q 1100N"
    assert result.barbecue_code == "WEBERQ_1100N_BL"
    assert result.barcode == ""


def test_description_product_uses_barbecue_code_without_import_id():
    source = ProductDescription(
        sku="WEBERQ_1100N_BL",
        import_id="",
        title="Weber® Q 1100N Gas Grill",
    )

    result = description_product_from_weber(source)

    assert result.description_key == "WEBERQ_1100N_BL"


def test_supplier_product_from_woocommerce():
    source = {
        "id": 16263,
        "sku": "1501061",
        "name": "Gāzes grils Weber Q1100N",
    }

    result = supplier_product_from_woocommerce(source)

    assert result.sku == "1501061"
    assert result.name == "Gāzes grils Weber Q1100N"
    assert result.producer == "Weber"


def test_supplier_product_requires_sku():
    with pytest.raises(ValueError, match="SKU"):
        supplier_product_from_woocommerce(
            {
                "id": 123,
                "sku": "",
                "name": "Weber Q1100N",
            }
        )


def test_supplier_product_requires_name():
    with pytest.raises(ValueError, match="name"):
        supplier_product_from_woocommerce(
            {
                "id": 123,
                "sku": "1501061",
                "name": "",
            }
        )
