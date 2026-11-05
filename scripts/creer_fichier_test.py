"""Crée un second jeu de test (« portefeuille B ») pour vérifier que le pipeline et l'application
fonctionnent sur un autre fichier : autres entreprises fictives, autre taille, autres erreurs,
et quelques lignes réellement invalides qui doivent partir en quarantaine.
Usage : python scripts/creer_fichier_test.py"""
import subprocess
import sys

import pandas as pd

TMP = "data/_tmp_portefeuille_B.csv"
subprocess.run([sys.executable, "scripts/generer_dataset.py", "2026", "18", TMP], check=True)
df = pd.read_csv(TMP, dtype=str)

new_names = ["Aubrac Énergies", "Belcastel Transports", "Cévenne Santé", "Dorlan Industries", "Esterel Foods",
             "Faraday & Pike plc", "Garonne Matériaux", "Hollis Software Inc.", "Iroise Hôtels", "Jasmet Retail",
             "Kerlan Télécom", "Lorvane Médias", "Marbella Cerámica", "Norrland Freight", "Orvieto Moda",
             "Pembroke Utilities", "Quercy Bio", "Rhenwald Auto"]
old_names = sorted(df["nom_entreprise"].unique(), key=lambda n: df.index[df["nom_entreprise"] == n][0])
df["nom_entreprise"] = df["nom_entreprise"].map(dict(zip(old_names, new_names)))
df["id_report"] = df["id_report"].str.replace("RPT-0", "RPT-B", regex=False)
df["id_entreprise"] = df["id_entreprise"].str.replace("ENT-0", "ENT-B", regex=False)
df["id_ligne"] = "B" + df["id_ligne"].str[1:]

# Bruit corrigeable supplémentaire
df.loc[df.index[5:9], "secteur"] = df.loc[df.index[5:9], "secteur"] + "  "     # espaces parasites
# Lignes invalides (à mettre en quarantaine)
df.loc[30, "date_saisie"] = "31/02/2026"            # date impossible
df.loc[120, "valeur_reference"] = "n.d."            # vérité terrain absente
df.loc[250, "devise"] = "YEN"                       # devise hors contrat
df.loc[400, "erreur_saisie"] = "0"                  # label contradictoire
df.loc[400, "valeur_saisie_manuelle"] = "999999"

df.to_csv("data/dataset_test_portefeuille_B.csv", index=False, encoding="utf-8-sig")
df.to_excel("data/dataset_test_portefeuille_B.xlsx", index=False)
subprocess.run(["rm", TMP], check=True)
print(f"Fichier de test : {len(df)} lignes, {df['id_report'].nunique()} rapports")
