from __future__ import annotations

from decimal import Decimal
from pathlib import Path


# ---------------------------------------------------------------------------
# Projekta pamatinformācija
# ---------------------------------------------------------------------------

PROJECT_NAME = "GrillAndMore Sync"
PROJECT_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Projekta mapes
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent

LOG_DIR = PROJECT_ROOT / "logs"
REPORT_DIR = PROJECT_ROOT / "reports"
DATA_DIR = PROJECT_ROOT / "data"
TEMP_DIR = PROJECT_ROOT / "tmp"


# ---------------------------------------------------------------------------
# Sinhronizācijas noklusējuma iestatījumi
# ---------------------------------------------------------------------------

DEFAULT_BRAND = "WEBER"

DEFAULT_DRY_RUN = True
DEFAULT_BATCH_SIZE = 100
DEFAULT_TIMEOUT = 30
DEFAULT_RETRY_COUNT = 3
DEFAULT_RETRY_DELAY = 2


# ---------------------------------------------------------------------------
# Cenu iestatījumi
# ---------------------------------------------------------------------------

VAT_RATE = Decimal("0.21")
VAT_MULTIPLIER = Decimal("1.21")

PRICE_DECIMAL_PLACES = Decimal("0.01")


# ---------------------------------------------------------------------------
# Atlikumu iestatījumi
# ---------------------------------------------------------------------------

DEFAULT_STOCK_QUANTITY = 0

MANAGE_STOCK = True
ALLOW_BACKORDERS = False


# ---------------------------------------------------------------------------
# WooCommerce iestatījumi
# ---------------------------------------------------------------------------

WOOCOMMERCE_PRODUCTS_PER_PAGE = 100

WOOCOMMERCE_STATUS_PUBLISH = "publish"
WOOCOMMERCE_STATUS_DRAFT = "draft"

WOOCOMMERCE_STOCK_STATUS_IN_STOCK = "instock"
WOOCOMMERCE_STOCK_STATUS_OUT_OF_STOCK = "outofstock"
WOOCOMMERCE_STOCK_STATUS_ON_BACKORDER = "onbackorder"


# ---------------------------------------------------------------------------
# Piegādātāja datu iestatījumi
# ---------------------------------------------------------------------------

SUPPLIER_SKU_FIELD = "catalogue_number"
SUPPLIER_NAME_FIELD = "name"
SUPPLIER_PRICE_FIELD = "price"
SUPPLIER_STOCK_FIELD = "instock"
SUPPLIER_BARCODE_FIELD = "barcode"
SUPPLIER_BRAND_FIELD = "producer"


# ---------------------------------------------------------------------------
# Failu un atskaišu iestatījumi
# ---------------------------------------------------------------------------

CSV_ENCODING = "utf-8-sig"
CSV_DELIMITER = ","

LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
REPORT_DATE_FORMAT = "%Y%m%d-%H%M%S"


# ---------------------------------------------------------------------------
# Konsoles izskats
# ---------------------------------------------------------------------------

SEPARATOR = "=" * 72
SUBSEPARATOR = "-" * 72

STATUS_OK = "PASS"
STATUS_WARNING = "WARNING"
STATUS_ERROR = "FAIL"

SYMBOL_OK = "✓"
SYMBOL_WARNING = "!"
SYMBOL_ERROR = "✗"


# ---------------------------------------------------------------------------
# Palīgfunkcijas
# ---------------------------------------------------------------------------

def ensure_project_directories() -> None:
    """
    Izveido projekta darba mapes, ja tās vēl nepastāv.
    """

    directories = (
        LOG_DIR,
        REPORT_DIR,
        DATA_DIR,
        TEMP_DIR,
    )

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)