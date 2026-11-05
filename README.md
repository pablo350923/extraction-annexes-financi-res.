# Extraction et contrôle des notes annexes financières

Projet de MSc – IA & Automatisation appliquées à la Finance.

**Question de projet (X/Y/Z)** : un outil d'extraction automatisée des notes annexes (X) peut-il réduire le temps de
traitement des rapports financiers et les erreurs de transcription (Y) par rapport à une recherche visuelle et une
saisie manuelle dans Excel (Z) ?

## Workflow

```
SOURCE → VALIDATE → CLEAN → TRANSFORM → EXTRACT → ÉCART DE CONTRÔLE → SEUIL → ALERTE → OUTPUT
```

Le contrôle reprend la logique « actifs → rendement → seuil → alerte » : pour chaque rapport, on calcule l'écart (%)
entre un total et la somme de ses composantes (CA = segments, dette brute = composantes, échéances, etc.) à partir des
**valeurs extraites**, et on alerte au-delà d'un seuil.

## Résultats sur le jeu synthétique (40 rapports, 800 champs)

| Scénario | Temps / rapport | Erreurs résiduelles |
|---|---|---|
| Saisie manuelle seule (baseline Z) | 30,1 min | 7,6 % |
| Saisie manuelle + alerte | 36,9 min | 1,25 % |
| Outil d'extraction + alerte (X) | < 1 s | 0 % (*) |

Seuil retenu : 0,1 % (84 % des erreurs détectées, 0 fausse alerte) ; le seuil de 4 % du modèle n'en détecte que 48 %.
(*) Le texte publié du jeu synthétique est propre : ce résultat doit être confirmé sur de vrais rapports PDF.

## Structure

| Fichier | Rôle |
|---|---|
| `pipeline.py` | Toute la logique, en fonctions. `run_pipeline("data/...csv")` lance tout |
| `notebook_pipeline.ipynb` | Cahier Python : chaque étape exécutée et commentée |
| `app.py` | Application web Streamlit (alertes, seuil, baseline, qualité des données) |
| `webapp_controle_annexes.html` | Même application en **un seul fichier HTML** : double-clic pour l'ouvrir. Le bouton « Importer » exécute `pipeline.py` dans le navigateur (Pyodide, connexion internet requise) |
| `data/` | Jeu de données synthétique (CSV standard + version Excel FR), dictionnaire de données, et **jeu de test « portefeuille B »** (CSV + Excel) pour vérifier l'import d'un autre fichier |
| `scripts/generer_dataset.py` | Régénère le jeu de données (graine fixe ; graine, taille et fichier de sortie paramétrables) |
| `scripts/creer_fichier_test.py` | Crée le jeu de test « portefeuille B » (24 rapports, autres entreprises, 4 lignes invalides) |
| `scripts/build_webapp.py` | Reconstruit la page HTML après une modification de `pipeline.py` |
| `tests/test_quarantaine.py` | Vérifie que les lignes invalides partent en quarantaine |

## Lancer le projet

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt

python pipeline.py                 # pipeline complet -> dossier outputs/
python tests/test_quarantaine.py   # test
jupyter notebook notebook_pipeline.ipynb
streamlit run app.py               # application web sur http://localhost:8501
```

## Tester avec un autre fichier

Dans la page HTML ou dans `streamlit run app.py`, importez `data/dataset_test_portefeuille_B.csv` (ou `.xlsx`) :
24 rapports, 486 lignes → 474 propres, **6 en quarantaine** (date impossible, valeur de référence absente, devise inconnue,
label contradictoire). Un fichier qui ne respecte pas le Data Contract (ex. `dictionnaire_donnees.csv`) est refusé avec un message clair.

## Limites
- Données entièrement synthétiques et fictives (aucune entreprise réelle).
- L'outil v0 lit le texte du chiffre déjà isolé ; la localisation dans le PDF reste à développer (prochaine étape).
- `LOC_INTERETS` et `TAUX_MOYEN_DETTE` ne sont couverts par aucune identité comptable : leurs erreurs ne déclenchent pas d'alerte.
