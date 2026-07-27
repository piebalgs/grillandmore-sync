"""Universālais GrillAndMore produkta datu modelis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProductFeature:
    """Viena produkta priekšrocība vai funkcija."""

    title: str
    description: str = ""

    def __post_init__(self) -> None:
        self.title = self.title.strip()
        self.description = self.description.strip()


@dataclass(slots=True)
class ProductImage:
    """Produkta attēls un tā metadati."""

    url: str
    alt_text: str = ""
    position: int = 0
    image_type: str = "product"

    def __post_init__(self) -> None:
        self.url = self.url.strip()
        self.alt_text = self.alt_text.strip()
        self.image_type = self.image_type.strip().lower()


@dataclass(slots=True)
class ProductDocument:
    """Ar produktu saistīts dokuments."""

    url: str
    title: str = ""
    document_type: str = ""

    def __post_init__(self) -> None:
        self.url = self.url.strip()
        self.title = self.title.strip()
        self.document_type = self.document_type.strip().lower()


@dataclass(slots=True)
class Product:
    """
    Universāls produkta modelis.

    Piegādātāju adapteri pārveido CSV, XML vai API datus šajā modelī.
    Pārējā GMPS sistēma strādā tikai ar Product objektiem.
    """

    # Obligātie identifikācijas lauki
    brand: str
    sku: str

    # Papildu identifikatori
    ean: str = ""
    mpn: str = ""
    import_id: str = ""
    supplier_id: str = ""

    # Pamatinformācija
    name: str = ""
    original_name: str = ""
    product_type: str = ""
    product_subtype: str = ""
    series: str = ""
    model: str = ""

    # Oriģinālais piegādātāja saturs
    supplier_description: str = ""
    supplier_short_description: str = ""

    # GrillAndMore saturs
    short_description: str = ""
    description_html: str = ""

    # Produkta īpašības
    features: list[ProductFeature] = field(default_factory=list)
    specifications: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, str] = field(default_factory=dict)

    # Saderība un komplektācija
    compatibility: list[str] = field(default_factory=list)
    package_contents: list[str] = field(default_factory=list)
    accessories: list[str] = field(default_factory=list)
    spare_parts: list[str] = field(default_factory=list)

    # Garantija
    warranty: dict[str, str] = field(default_factory=dict)

    # Multivide
    images: list[ProductImage] = field(default_factory=list)
    documents: list[ProductDocument] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)

    # WooCommerce
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status: str = "draft"

    # SEO
    seo_title: str = ""
    seo_description: str = ""
    seo_keywords: list[str] = field(default_factory=list)

    # GMPS kvalitātes kontrole
    gmps_score: int = 0
    gmps_level: str = "basic"
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)

    # Neapstrādāti piegādātāja dati
    source_file: str = ""
    source_category: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalizē galvenos teksta laukus un pārbauda obligātos datus."""

        self.brand = self.brand.strip()
        self.sku = self.sku.strip()
        self.ean = self.ean.strip()
        self.mpn = self.mpn.strip()
        self.import_id = self.import_id.strip()
        self.name = self.name.strip()
        self.original_name = self.original_name.strip()
        self.product_type = self.product_type.strip().lower()
        self.series = self.series.strip()
        self.model = self.model.strip()
        self.status = self.status.strip().lower()

        if not self.brand:
            raise ValueError("Produkta zīmols nedrīkst būt tukšs.")

        if not self.sku:
            raise ValueError("Produkta SKU nedrīkst būt tukšs.")

        if self.gmps_score < 0 or self.gmps_score > 100:
            raise ValueError("GMPS vērtējumam jābūt diapazonā no 0 līdz 100.")

    @property
    def display_name(self) -> str:
        """Atgriež pilnu produkta nosaukumu ar zīmolu."""

        if not self.name:
            return f"{self.brand} {self.sku}".strip()

        if self.name.lower().startswith(self.brand.lower()):
            return self.name

        return f"{self.brand} {self.name}".strip()

    @property
    def primary_image(self) -> ProductImage | None:
        """Atgriež pirmo produkta attēlu."""

        if not self.images:
            return None

        return sorted(self.images, key=lambda image: image.position)[0]

    def add_feature(self, title: str, description: str = "") -> None:
        """Pievieno produktam funkciju, ja tās virsraksts nav tukšs."""

        title = title.strip()
        description = description.strip()

        if title:
            self.features.append(
                ProductFeature(
                    title=title,
                    description=description,
                )
            )

    def add_image(
        self,
        url: str,
        alt_text: str = "",
        position: int | None = None,
        image_type: str = "product",
    ) -> None:
        """Pievieno pilnu HTTP vai HTTPS attēla URL."""

        url = url.strip()

        if not url.startswith(("http://", "https://")):
            return

        if any(image.url == url for image in self.images):
            return

        resolved_position = (
            position if position is not None else len(self.images)
        )

        self.images.append(
            ProductImage(
                url=url,
                alt_text=alt_text,
                position=resolved_position,
                image_type=image_type,
            )
        )