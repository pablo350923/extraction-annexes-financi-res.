"""Injecte 4 lignes invalides et vérifie qu'elles partent en quarantaine.
Lancer depuis la racine du projet :  python tests/test_quarantaine.py"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import run_pipeline  # noqa: E402

df = pd.read_csv("data/dataset_extraction_annexes_financieres.csv", dtype=str)
df.loc[0, "date_saisie"] = "fin mars"                    # date illisible -> C3c
df.loc[200, "valeur_reference"] = "n.d."                 # vérité terrain inutilisable -> D2 (+ C1)
df.loc[400, "erreur_saisie"] = "1"                       # label faux -> C4
df.loc[600, "mise_en_page_tableau"] = "tableau bizarre"  # hors liste -> D1
corrupted = Path("outputs_test/dataset_corrompu.csv")
corrupted.parent.mkdir(exist_ok=True)
df.to_csv(corrupted, index=False)

results = run_pipeline(corrupted, output_folder="outputs_test")
quarantined = set(results["04_quarantaine"]["id_ligne"])
expected = {"L0001", "L0201", "L0401", "L0601"}
assert expected <= quarantined, f"Lignes attendues en quarantaine manquantes : {expected - quarantined}"
print("\nTEST OK :", sorted(quarantined))
