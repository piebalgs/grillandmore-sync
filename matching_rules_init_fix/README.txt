MATCHING RULES INIT FIX
=======================

Mērķis
------
Novērst pytest collection ImportError, ko izraisīja rules/__init__.py mēģinājums
importēt neesošas MAXIMUM_POINTS konstantes no producer.py un series.py.

Labojums
--------
Mainīts tikai:

    src/descriptions/matching/rules/__init__.py

Fails tagad eksportē tikai publiskās funkcijas. Esošie scoring noteikumi,
punktu konstantes un DEFAULT_RULES netiek mainīti.

Uzstādīšana projekta saknē
--------------------------

    unzip -o ~/Downloads/matching_rules_init_fix.zip -d .

Pirmā pārbaude
--------------

    python3 -m py_compile src/descriptions/matching/rules/__init__.py

Pilnais matching tests
----------------------

    pytest -q tests/descriptions/matching

Ja matching testi ir zaļi, tad palaid visu projektu:

    pytest -q
