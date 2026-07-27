EAN COMPATIBILITY FIX
=====================

Šis labojums novērš 3 testu kļūdas.

Problēma:
Iepriekšējais arhīvs aizvietoja esošos četrus DEFAULT_RULES ar:
- score_ean
- score_model_code

Labojums:
- atjauno visus četrus esošos noklusējuma noteikumus;
- saglabā EAN ekspertu kā opt-in noteikumu;
- atjauno rules/__init__.py eksportus;
- aizvieto iepriekš pievienoto EAN integrācijas testu.

Kopē projekta saknē:

    unzip -o ~/Downloads/matching_ean_compatibility_fix.zip -d .

Pārbaudi:

    python3 -m py_compile       src/descriptions/matching/scoring.py       src/descriptions/matching/rules/__init__.py

    pytest -q tests/descriptions/matching

EAN izmantošana šajā posmā:

    calculate_score(
        description,
        supplier,
        rules=(score_ean, *DEFAULT_RULES),
    )
