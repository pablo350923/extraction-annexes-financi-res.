"""
Pipeline SOURCE -> VALIDATE -> CLEAN -> TRANSFORM -> OUTPUT
Projet : extraction des notes annexes de rapports annuels.
Baseline mesurée = saisie manuelle (Ctrl+F + saisie Excel).

Source de vérité : dictionnaire_donnees.csv + Data Contract (règles C1 à C5).
Les éléments marqués [SUGGESTION] ne viennent pas du contrat.

Utilisation :
    from pipeline import run_pipeline
    results = run_pipeline("data/dataset_extraction_annexes_financieres.csv")
"""
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

# =============================================================================
# DATA CONTRACT (traduit en paramètres Python)
# =============================================================================
EXPECTED_COLUMNS = [
    "id_ligne", "id_report", "id_entreprise", "nom_entreprise", "secteur", "pays",
    "referentiel_comptable", "exercice", "devise", "langue_rapport", "nb_pages_rapport",
    "section_annexe", "numero_note", "page_note", "mise_en_page_tableau", "code_champ",
    "libelle_dans_rapport", "echelle_publiee", "texte_brut_publie", "valeur_reference",
    "unite_reference", "valeur_saisie_manuelle", "erreur_saisie", "type_erreur",
    "temps_saisie_sec", "id_analyste", "date_saisie",
]
NUMERIC_COLUMNS = ["exercice", "nb_pages_rapport", "numero_note", "page_note",
                   "valeur_reference", "valeur_saisie_manuelle", "erreur_saisie",
                   "temps_saisie_sec"]

SECTEURS = ["Industrie", "Transport & Logistique", "Santé", "Énergie", "Distribution",
            "Agroalimentaire", "Télécoms", "Technologie", "Matériaux", "Loisirs & Hôtellerie",
            "Immobilier", "Biens de consommation", "Médias", "Automobile"]
DEVISES = ["EUR", "GBP", "USD", "CHF"]
ALLOWED_VALUES = {  # valeurs autorisées du dictionnaire de données
    "referentiel_comptable": ["IFRS", "US GAAP"],
    "langue_rapport": ["FR", "EN"],
    "mise_en_page_tableau": ["simple", "multi-colonnes N/N-1", "imbriqué", "scanné/image"],
    "echelle_publiee": ["millions", "milliers", "pourcentage"],
    "type_erreur": ["aucune", "transposition", "mauvaise_colonne_N-1", "arrondi",
                    "omission", "signe", "mauvaise_echelle"],
    "code_champ": ["CA_SEG_1", "CA_SEG_2", "CA_SEG_3", "CA_TOTAL", "CA_ZONE_EUROPE",
                   "CA_ZONE_AMERIQUES", "CA_ZONE_RDM", "DETTE_OBLIGATAIRE", "DETTE_BANCAIRE",
                   "DETTE_LOCATIVE", "DETTE_BRUTE", "TRESORERIE", "DETTE_NETTE",
                   "ECHEANCE_MOINS_1AN", "ECHEANCE_1_5ANS", "ECHEANCE_PLUS_5ANS",
                   "TAUX_MOYEN_DETTE", "LOC_COURANT", "LOC_NON_COURANT", "LOC_INTERETS"],
}

# C1 – identités comptables : total = somme des composantes
IDENTITIES = {
    "CA_TOTAL = somme des segments": ("CA_TOTAL", ["CA_SEG_1", "CA_SEG_2", "CA_SEG_3"]),
    "CA_TOTAL = somme des zones": ("CA_TOTAL", ["CA_ZONE_EUROPE", "CA_ZONE_AMERIQUES", "CA_ZONE_RDM"]),
    "DETTE_BRUTE = oblig. + bancaire + location": ("DETTE_BRUTE", ["DETTE_OBLIGATAIRE", "DETTE_BANCAIRE", "DETTE_LOCATIVE"]),
    "DETTE_BRUTE = somme des échéances": ("DETTE_BRUTE", ["ECHEANCE_MOINS_1AN", "ECHEANCE_1_5ANS", "ECHEANCE_PLUS_5ANS"]),
    "DETTE_BRUTE = DETTE_NETTE + TRESORERIE": ("DETTE_BRUTE", ["DETTE_NETTE", "TRESORERIE"]),
    "DETTE_LOCATIVE = courant + non courant": ("DETTE_LOCATIVE", ["LOC_COURANT", "LOC_NON_COURANT"]),
}
# "À l'arrondi près" = 1 unité d'affichage (0,1 M si publié en millions, 1 millier sinon)
ROUNDING_UNIT = {"millions": 0.1, "milliers": 0.001}

# C5 – plages
TEMPS_MIN, TEMPS_MAX = 10, 900          # secondes
TAUX_MIN, TAUX_MAX = 0, 15              # %
ENCOURS = ["DETTE_OBLIGATAIRE", "DETTE_BANCAIRE", "DETTE_LOCATIVE", "DETTE_BRUTE",
           "ECHEANCE_MOINS_1AN", "ECHEANCE_1_5ANS", "ECHEANCE_PLUS_5ANS",
           "LOC_COURANT", "LOC_NON_COURANT"]  # DETTE_NETTE peut être négative (trésorerie nette)

# Corrections autorisées (C3) : uniquement des variantes sans ambiguïté
SECTEUR_MAP = {"Sante": "Santé", "Healthcare": "Santé", "industrie": "Industrie",
               "Industrials": "Industrie", "Tech": "Technologie", "Retail": "Distribution"}
DEVISE_MAP = {"€": "EUR", "$": "USD", "£": "GBP"}

# Gravité : "corrigeable" = traité par CLEAN (quarantaine si toujours en échec après),
#           "bloquant"    = quarantaine,
#           "avertissement" = ligne conservée mais signalée.
RULES = {
    "D1": ("Colonnes catégorielles dans les valeurs autorisées", "bloquant"),
    "D2": ("valeur_reference présente et numérique", "bloquant"),
    "D3": ("page_note renseignée", "avertissement"),
    "C1": ("Identités comptables respectées à l'arrondi près", "bloquant"),
    "C2a": ("Pas de doublon exact", "corrigeable"),
    "C2b": ("Pas deux contenus différents pour la même clé (id_report, code_champ)", "bloquant"),
    "C3a": ("Secteur dans la liste de référence", "corrigeable"),
    "C3b": ("Devise au format ISO", "corrigeable"),
    "C3c": ("Date au format AAAA-MM-JJ", "corrigeable"),
    "C4": ("Label cohérent : erreur_saisie=1 si et seulement si saisie ≠ référence ou vide", "bloquant"),
    "C5a": (f"Temps de saisie renseigné et entre {TEMPS_MIN} et {TEMPS_MAX} s", "avertissement"),
    "C5b": (f"Taux moyen entre {TAUX_MIN} et {TAUX_MAX} %", "bloquant"),
    "C5c": ("Encours de dette >= 0", "bloquant"),
}


def to_number(series):
    """Convertit en nombre (accepte la virgule décimale). Invalide -> NaN."""
    return pd.to_numeric(series.astype("string").str.replace(",", ".", regex=False), errors="coerce")


# =============================================================================
# 1. SOURCE
# =============================================================================
def load_source(path):
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str)
    else:
        # détecte la version "Excel FR" (séparateur ;)
        with open(path, encoding="utf-8-sig") as f:
            sep = ";" if ";" in f.readline() else ","
        df = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-8-sig")
    # On lit tout en texte : les types sont convertis explicitement dans CLEAN.

    print(f"[SOURCE] {path.name} : {df.shape[0]} lignes, {df.shape[1]} colonnes")
    print(df.head())

    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    extra = [c for c in df.columns if c not in EXPECTED_COLUMNS]
    if missing:
        raise ValueError(f"Colonnes attendues absentes : {missing}")
    if extra:
        print(f"[SOURCE] Colonnes non prévues par le contrat (conservées) : {extra}")
    return df


# =============================================================================
# 2. VALIDATE
# =============================================================================
def _failures(df, mask, rule, reason):
    """Lignes en échec pour une règle, avec la raison (texte ou Series)."""
    out = df.loc[mask, ["id_ligne"]].copy()
    out["regle"] = rule
    out["gravite"] = RULES[rule][1]
    out["raison"] = reason[mask] if isinstance(reason, pd.Series) else reason
    return out


def check_identities(df):
    ref = to_number(df["valeur_reference"])
    table = (df.assign(v=ref)
               .pivot_table(index="id_report", columns="code_champ", values="v", aggfunc="first"))
    scale = (df[df["echelle_publiee"] != "pourcentage"]
             .groupby("id_report")["echelle_publiee"].first().map(ROUNDING_UNIT))
    rows = []
    for name, (total, parts) in IDENTITIES.items():
        gap = table[total] - table[parts].sum(axis=1, min_count=len(parts))
        tolerance = scale.reindex(table.index).fillna(0.1) + 1e-9
        bad = gap.isna() | (gap.abs() > tolerance)
        for rep in gap[bad].index:
            reason = (f"{name} : champ manquant" if pd.isna(gap[rep])
                      else f"{name} : écart de {gap[rep]:.3f} M")
            mask = (df["id_report"] == rep) & df["code_champ"].isin([total] + parts)
            rows.append(_failures(df, mask, "C1", reason))
    return rows


def validate(df):
    """Applique toutes les règles. Ne modifie pas df. Renvoie (rapport, détail)."""
    f = []
    ref = to_number(df["valeur_reference"])
    manual = to_number(df["valeur_saisie_manuelle"])
    temps = to_number(df["temps_saisie_sec"])

    # D1 – valeurs autorisées (dictionnaire de données)
    for col, allowed in ALLOWED_VALUES.items():
        bad = ~df[col].isin(allowed)
        f.append(_failures(df, bad, "D1", f"{col} hors liste : " + df[col].astype(str)))
    # D2 – vérité terrain exploitable
    f.append(_failures(df, ref.isna(), "D2", "valeur_reference vide ou non numérique"))
    # D3 – page de la note
    f.append(_failures(df, df["page_note"].isna(), "D3", "page_note vide"))

    # C1 – identités comptables
    f.extend(check_identities(df))

    # C2 – doublons
    content_cols = [c for c in df.columns if c != "id_ligne"]
    exact = df.duplicated(subset=content_cols, keep=False)
    same_key = df.duplicated(subset=["id_report", "code_champ"], keep=False)
    f.append(_failures(df, exact, "C2a", "doublon exact d'une autre ligne"))
    f.append(_failures(df, same_key & ~exact, "C2b", "même clé, contenu différent"))

    # C3 – libellés et formats
    f.append(_failures(df, ~df["secteur"].isin(SECTEURS), "C3a", "secteur non standard : " + df["secteur"].astype(str)))
    f.append(_failures(df, ~df["devise"].isin(DEVISES), "C3b", "devise non ISO : " + df["devise"].astype(str)))
    iso = pd.to_datetime(df["date_saisie"], format="%Y-%m-%d", errors="coerce")
    f.append(_failures(df, iso.isna(), "C3c", "date non ISO : " + df["date_saisie"].astype(str)))

    # C4 – cohérence du label (tolérance numérique minime)
    differs = manual.isna() | ((manual - ref).abs() > 1e-6)
    label = to_number(df["erreur_saisie"])
    incoherent = (differs != (label == 1)) | ((label == 1) != (df["type_erreur"] != "aucune"))
    f.append(_failures(df, incoherent, "C4", "label erreur_saisie / type_erreur incohérent avec les valeurs"))

    # C5 – plages
    bad_t = temps.isna() | (temps < TEMPS_MIN) | (temps > TEMPS_MAX)
    reason_t = np.where(temps.isna(), "temps manquant", "temps hors plage : " + df["temps_saisie_sec"].astype(str) + " s")
    f.append(_failures(df, bad_t, "C5a", pd.Series(reason_t, index=df.index)))
    is_rate = df["code_champ"] == "TAUX_MOYEN_DETTE"
    f.append(_failures(df, is_rate & ((ref < TAUX_MIN) | (ref > TAUX_MAX)), "C5b", "taux hors plage"))
    f.append(_failures(df, df["code_champ"].isin(ENCOURS) & (ref < 0), "C5c", "encours négatif"))

    details = pd.concat(f, ignore_index=True)
    return summarise(details), details


def summarise(details):
    rows = []
    for rule, (label, severity) in RULES.items():
        ids = details.loc[details["regle"] == rule, "id_ligne"].unique()
        shown = ", ".join(ids[:10]) + (" …" if len(ids) > 10 else "")
        rows.append({"regle": rule, "description": label, "gravite": severity,
                     "nb_echecs": len(ids), "lignes_concernees": shown})
    return pd.DataFrame(rows)


# =============================================================================
# 3. CLEAN
# =============================================================================
def clean(raw):
    df = raw.copy()
    log = []

    def note(action, column, ids, detail=""):
        log.append({"action": action, "colonne": column, "nb_lignes": len(ids),
                    "lignes": ", ".join(list(ids)[:15]) + (" …" if len(ids) > 15 else ""),
                    "detail": detail})

    # Espaces superflus dans les textes
    for col in df.columns:
        stripped = df[col].str.strip()
        changed = df[col].notna() & (stripped != df[col])
        if changed.any():
            note("suppression des espaces", col, df.loc[changed, "id_ligne"])
            df[col] = stripped

    # C3a – secteur
    to_fix = df["secteur"].isin(SECTEUR_MAP)
    note("standardisation du libellé", "secteur", df.loc[to_fix, "id_ligne"], str(SECTEUR_MAP))
    df["secteur"] = df["secteur"].replace(SECTEUR_MAP)

    # C3b – devise
    to_fix = df["devise"].isin(DEVISE_MAP)
    note("symbole remplacé par code ISO", "devise", df.loc[to_fix, "id_ligne"], str(DEVISE_MAP))
    df["devise"] = df["devise"].replace(DEVISE_MAP)

    # C3c – dates : ISO d'abord, puis JJ/MM/AAAA (seul autre format observé)
    iso = pd.to_datetime(df["date_saisie"], format="%Y-%m-%d", errors="coerce")
    fr = pd.to_datetime(df["date_saisie"], format="%d/%m/%Y", errors="coerce")
    converted = iso.isna() & fr.notna()
    note("date JJ/MM/AAAA convertie en AAAA-MM-JJ", "date_saisie", df.loc[converted, "id_ligne"])
    parsed = iso.fillna(fr)
    df.loc[parsed.notna(), "date_saisie"] = parsed[parsed.notna()].dt.strftime("%Y-%m-%d")
    # les dates illisibles restent telles quelles -> C3c en échec -> quarantaine

    # Types numériques
    for col in NUMERIC_COLUMNS:
        converted = to_number(df[col])
        lost = df[col].notna() & converted.isna()
        if lost.any():
            note("valeur non numérique remplacée par vide", col, df.loc[lost, "id_ligne"],
                 "valeurs d'origine conservées dans la table de quarantaine")
        df[col] = converted
    for col in ["exercice", "nb_pages_rapport", "numero_note", "page_note", "erreur_saisie", "temps_saisie_sec"]:
        df[col] = df[col].astype("Int64")

    # C2a – doublons exacts : on garde la première occurrence
    content_cols = [c for c in df.columns if c != "id_ligne"]
    dup = df.duplicated(subset=content_cols, keep="first")
    note("doublon exact supprimé (1re occurrence conservée)", "toutes", df.loc[dup, "id_ligne"])
    df = df[~dup].copy()

    # Re-validation après correction : ce qui échoue encore est mis en quarantaine
    # (sauf les avertissements, qui restent dans le jeu propre avec un indicateur).
    report_after, details_after = validate(df.astype({c: "string" for c in NUMERIC_COLUMNS}))
    blocking = details_after[details_after["gravite"] != "avertissement"]
    reasons = blocking.groupby("id_ligne")["raison"].agg(" | ".join).rename("motif_quarantaine")
    quarantine = raw[raw["id_ligne"].isin(reasons.index)].merge(reasons, on="id_ligne")
    note("mise en quarantaine", "toutes", quarantine["id_ligne"])

    clean_df = df[~df["id_ligne"].isin(reasons.index)].copy()
    warn = details_after[details_after["gravite"] == "avertissement"]
    clean_df["alerte_temps"] = clean_df["id_ligne"].isin(warn.loc[warn["regle"] == "C5a", "id_ligne"])
    clean_df["alerte_page"] = clean_df["id_ligne"].isin(warn.loc[warn["regle"] == "D3", "id_ligne"])
    note("alerte ajoutée (ligne conservée)", "alerte_temps", clean_df.loc[clean_df["alerte_temps"], "id_ligne"],
         "temps manquant ou hors plage : exclu des indicateurs de temps")

    log_df = pd.DataFrame(log)
    log_df = log_df[log_df["nb_lignes"] > 0].reset_index(drop=True)
    return clean_df, quarantine, log_df, report_after, int(dup.sum())


# =============================================================================
# 4. TRANSFORM   (toutes les variables ci-dessous sont des [SUGGESTION]s)
# =============================================================================
MATERIALITY_PCT = 1.0  # [SUGGESTION] seuil d'erreur "significative" pour un analyste


def transform(clean_df):
    df = clean_df.copy()

    # Écart de saisie (M devise) : ampleur de l'erreur de transcription
    df["ecart_saisie"] = df["valeur_saisie_manuelle"] - df["valeur_reference"]

    # Écart relatif (%) : rend comparables des erreurs sur des montants très différents
    df["ecart_relatif_pct"] = (df["ecart_saisie"].abs()
                               / df["valeur_reference"].abs().replace(0, np.nan) * 100)

    # Erreur significative : écart > 1 % ou chiffre oublié -> risque réel pour la valorisation
    df["erreur_significative"] = (df["valeur_saisie_manuelle"].isna()
                                  | (df["ecart_relatif_pct"] > MATERIALITY_PCT)).astype(int)

    # Temps retenu : le temps mesuré, sauf s'il est manquant ou aberrant (interruption)
    df["temps_retenu_sec"] = df["temps_saisie_sec"].where(~df["alerte_temps"])

    # Tableau complexe : facteur de difficulté attendu pour l'extraction
    df["tableau_complexe"] = df["mise_en_page_tableau"].isin(["imbriqué", "scanné/image"]).astype(int)

    # Indicateurs par rapport = les deux résultats mesurables du projet (temps, exactitude)
    per_report = (df.groupby("id_report")
                    .agg(nom_entreprise=("nom_entreprise", "first"),
                         exercice=("exercice", "first"),
                         mise_en_page_tableau=("mise_en_page_tableau", "first"),
                         echelle_publiee=("echelle_publiee", lambda s: s[s != "pourcentage"].iloc[0]),
                         nb_pages_rapport=("nb_pages_rapport", "first"),
                         nb_champs=("code_champ", "count"),
                         nb_erreurs=("erreur_saisie", "sum"),
                         nb_erreurs_significatives=("erreur_significative", "sum"),
                         temps_mesure_sec=("temps_retenu_sec", "sum"),
                         nb_temps_exclus=("temps_retenu_sec", lambda s: s.isna().sum()),
                         temps_moyen_par_champ_sec=("temps_retenu_sec", "mean"))
                    .reset_index())
    per_report["taux_erreur_pct"] = per_report["nb_erreurs"] / per_report["nb_champs"] * 100
    # Temps estimé : moyenne par champ x nb de champs (compense les temps exclus)
    per_report["temps_estime_min"] = per_report["temps_moyen_par_champ_sec"] * per_report["nb_champs"] / 60

    # Synthèse de la baseline, par type de tableau et au total
    def baseline(g):
        return pd.Series({"nb_rapports": len(g),
                          "temps_median_par_rapport_min": g["temps_estime_min"].median(),
                          "temps_moyen_par_rapport_min": g["temps_estime_min"].mean(),
                          "taux_erreur_pct": g["nb_erreurs"].sum() / g["nb_champs"].sum() * 100})
    summary = per_report.groupby("mise_en_page_tableau").apply(baseline, include_groups=False)
    summary.loc["TOTAL"] = baseline(per_report)
    return df, per_report, summary.round(2).reset_index()


# =============================================================================
# 4b. EXTRACT -> CONTROL GAP -> THRESHOLD -> ALERT
#     Même logique que le modèle du cours : actifs -> rendement -> seuil 4 % -> alerte
#     Ici : rapports -> écart de rapprochement (total vs somme des composantes) -> seuil -> alerte
# =============================================================================
THRESHOLD_PCT = 0.1                         # [SUGGESTION] seuil retenu après calibrage
CANDIDATE_THRESHOLDS = [4, 2, 1, 0.5, 0.1]  # 4 % = valeur du modèle du cours
HIGH_ALERT_PCT = 4                          # [SUGGESTION] au-delà : alerte "ÉLEVÉE"


def parse_published_number(text, scale, lang):
    """Extraction v0 : texte imprimé -> valeur en M devise (ou en %).
    Renvoie NaN si le texte n'a pas un format reconnu (=> alerte 'champ manquant')."""
    s = str(text).strip().replace(" ", " ").replace("\xa0", " ")
    if scale == "pourcentage":
        s = s.replace("%", "").replace(" ", "").replace(",", ".")
        return float(s) if re.fullmatch(r"\d+(\.\d+)?", s) else np.nan
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    # FR : "1 234,5"   EN : "1,234.5"
    s = s.replace(" ", "").replace(",", ".") if lang == "FR" else s.replace(",", "")
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return np.nan
    value = -float(s) if negative else float(s)
    return value / 1000 if scale == "milliers" else value


def extract(df):
    """Étape 3 : applique l'outil d'extraction v0 et mesure son exactitude."""
    df = df.copy()
    start = time.perf_counter()
    df["valeur_extraite_outil"] = [parse_published_number(t, s, l) for t, s, l in
                                   zip(df["texte_brut_publie"], df["echelle_publiee"], df["langue_rapport"])]
    runtime_sec = time.perf_counter() - start
    df["erreur_outil"] = (df["valeur_extraite_outil"].isna()
                          | ((df["valeur_extraite_outil"] - df["valeur_reference"]).abs() > 1e-6)).astype(int)
    return df, runtime_sec


def control_gaps(df, value_col, error_col, source):
    """Étape 4 : écart de chaque identité comptable, calculé sur les valeurs extraites.
    error_col sert uniquement à évaluer l'alerte (vérité terrain), pas à la déclencher."""
    # Un champ absent (ex. mis en quarantaine) reste NaN -> alerte "champ non extrait"
    reports, fields = df["id_report"].unique(), ALLOWED_VALUES["code_champ"]
    values = (df.pivot_table(index="id_report", columns="code_champ", values=value_col, aggfunc="first", dropna=False)
                .reindex(index=reports, columns=fields))
    errors = (df.pivot_table(index="id_report", columns="code_champ", values=error_col, aggfunc="first")
                .reindex(index=reports, columns=fields).fillna(1))
    unit = (df[df["echelle_publiee"] != "pourcentage"]
            .groupby("id_report")["echelle_publiee"].first().map(ROUNDING_UNIT))
    # note et page : identiques pour tous les champs d'une même section
    location = df.groupby(["id_report", "section_annexe"])[["numero_note", "page_note"]].first()

    tables = []
    for name, (total, parts) in IDENTITIES.items():
        t = values[total]
        s = values[parts].sum(axis=1, min_count=len(parts))
        out = pd.DataFrame({
            "source": source, "id_report": values.index, "controle": name,
            "champs_controles": ", ".join([total] + parts),
            "total": t.values, "somme_composantes": s.values,
        })
        out["ecart"] = out["total"] - out["somme_composantes"]
        out["ecart_pct"] = out["ecart"].abs() / out["total"].abs() * 100
        out["unite_arrondi"] = unit.reindex(values.index).values
        # tous les champs d'une identité sont dans la même note annexe
        section = (df[df["code_champ"].isin([total] + parts)]
                   .groupby("id_report")["section_annexe"].first().reindex(values.index))
        keys = list(zip(values.index, section))
        out["numero_note"] = location["numero_note"].reindex(keys).values
        out["page_note"] = location["page_note"].reindex(keys).values
        out["erreur_reelle"] = (errors[[total] + parts].sum(axis=1) > 0).values
        tables.append(out)
    return pd.concat(tables, ignore_index=True)


def is_alert(gaps, threshold_pct):
    """Étape 5 : alerte si un champ manque, ou si l'écart dépasse le seuil ET l'arrondi."""
    missing = gaps["ecart"].isna()
    beyond = (gaps["ecart_pct"] > threshold_pct) & (gaps["ecart"].abs() > gaps["unite_arrondi"] + 1e-9)
    return missing | beyond


def calibrate(gaps, thresholds=CANDIDATE_THRESHOLDS):
    """Étape 5 : compare plusieurs seuils grâce au label erreur_saisie."""
    rows = []
    for th in thresholds:
        alert = is_alert(gaps, th)
        true_pos = int((alert & gaps["erreur_reelle"]).sum())
        rows.append({"seuil_pct": th, "nb_alertes": int(alert.sum()), "vraies_alertes": true_pos,
                     "fausses_alertes": int((alert & ~gaps["erreur_reelle"]).sum()),
                     "erreurs_ratees": int((~alert & gaps["erreur_reelle"]).sum()),
                     "taux_detection_pct": round(true_pos / max(gaps["erreur_reelle"].sum(), 1) * 100, 1)})
    return pd.DataFrame(rows)


def build_alerts(gaps, threshold_pct=THRESHOLD_PCT):
    """Étape 6 : une ligne lisible par alerte."""
    a = gaps[is_alert(gaps, threshold_pct)].copy()
    a["niveau"] = np.where(a["ecart"].isna() | (a["ecart_pct"] > HIGH_ALERT_PCT), "ÉLEVÉ", "MOYEN")
    a["message"] = np.where(
        a["ecart"].isna(),
        a["id_report"] + " – " + a["controle"] + " : un champ n'a pas été extrait",
        a["id_report"] + " – " + a["controle"] + " : écart de "
        + a["ecart"].round(3).astype(str) + " M (" + a["ecart_pct"].round(2).astype(str) + " %)")
    as_text = lambda s: s.map(lambda x: "?" if pd.isna(x) else str(int(x))).astype(str)  # inconnue -> "?"
    a["action"] = ("Revérifier la note " + as_text(a["numero_note"])
                   + " (p. " + as_text(a["page_note"]) + ") : " + a["champs_controles"])
    cols = ["niveau", "source", "id_report", "controle", "ecart", "ecart_pct", "message", "action",
            "champs_controles", "erreur_reelle"]
    a["_ordre"] = (a["niveau"] == "MOYEN").astype(int)  # ÉLEVÉ en premier
    return a.sort_values(["_ordre", "ecart_pct"], ascending=[True, False])[cols].reset_index(drop=True)


def flagged_fields(alerts):
    """Ensemble (id_report, code_champ) que l'analyste va revérifier suite aux alertes."""
    pairs = set()
    for rep, champs in zip(alerts["id_report"], alerts["champs_controles"]):
        pairs.update((rep, c) for c in champs.split(", "))
    return pairs


def compare_with_baseline(df, per_report, alerts_manual, alerts_tool, runtime_sec):
    """Étape 7 : temps par rapport et taux d'erreur, avec et sans outil/alerte.
    [HYPOTHÈSE] revérifier un champ signalé prend le temps manuel moyen d'un champ."""
    n_reports, n_fields = df["id_report"].nunique(), len(df)
    sec_per_field = per_report["temps_moyen_par_champ_sec"].mean()
    manual_min = per_report["temps_estime_min"].mean()
    key = list(zip(df["id_report"], df["code_champ"]))

    def residual_error(error_col, alerts):
        reviewed = flagged_fields(alerts)
        missed = np.array([k not in reviewed for k in key]) & (df[error_col] == 1).to_numpy()
        return missed.sum() / n_fields * 100

    def review_min(alerts):
        return len(flagged_fields(alerts)) * sec_per_field / 60 / n_reports

    rows = [
        ("Saisie manuelle seule (baseline Z)", manual_min, df["erreur_saisie"].mean() * 100),
        ("Saisie manuelle + alerte", manual_min + review_min(alerts_manual),
         residual_error("erreur_saisie", alerts_manual)),
        ("Outil d'extraction seul", runtime_sec / 60 / n_reports, df["erreur_outil"].mean() * 100),
        ("Outil d'extraction + alerte (X)", runtime_sec / 60 / n_reports + review_min(alerts_tool),
         residual_error("erreur_outil", alerts_tool)),
    ]
    return pd.DataFrame(rows, columns=["scenario", "temps_par_rapport_min", "taux_erreur_residuel_pct"]).round(3)


def export_alerts_excel(alerts, path):
    """Alerte visible : fichier Excel avec lignes en rouge (ÉLEVÉ) ou orange (MOYEN)."""
    colors = {"ÉLEVÉ": "background-color: #F8CBAD", "MOYEN": "background-color: #FFE699"}
    styled = alerts.drop(columns="erreur_reelle").style.apply(
        lambda row: [colors[row["niveau"]]] * len(row), axis=1)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        styled.to_excel(writer, sheet_name="Alertes", index=False)
        sheet = writer.sheets["Alertes"]
        for col, width in zip("ABCDEFGHI", [8, 8, 10, 40, 10, 10, 70, 90, 50]):
            sheet.column_dimensions[col].width = width


def run_alerting(transformed, per_report, threshold_pct=THRESHOLD_PCT):
    df, runtime_sec = extract(transformed)
    gaps_manual = control_gaps(df, "valeur_saisie_manuelle", "erreur_saisie", "manuel")
    gaps_tool = control_gaps(df, "valeur_extraite_outil", "erreur_outil", "outil")
    calibration = calibrate(gaps_manual)
    alerts_manual = build_alerts(gaps_manual, threshold_pct)
    alerts_tool = build_alerts(gaps_tool, threshold_pct)
    comparison = compare_with_baseline(df, per_report, alerts_manual, alerts_tool, runtime_sec)
    return {"df": df, "gaps": pd.concat([gaps_manual, gaps_tool], ignore_index=True),
            "calibration": calibration, "alerts": pd.concat([alerts_manual, alerts_tool], ignore_index=True),
            "comparison": comparison}


# =============================================================================
# 5. OUTPUT
# =============================================================================
def export(outputs, folder):
    folder = Path(folder)
    folder.mkdir(exist_ok=True)
    for name, table in outputs.items():
        table.to_csv(folder / f"{name}.csv", index=False, encoding="utf-8-sig")
    print(f"[OUTPUT] {len(outputs)} fichiers CSV écrits dans {folder.resolve()}")


def run_pipeline(path, output_folder="outputs", threshold_pct=THRESHOLD_PCT):
    raw = load_source(path)
    report_before, details = validate(raw)
    clean_df, quarantine, log, report_after, n_dup = clean(raw)
    transformed, per_report, baseline = transform(clean_df)
    alerting = run_alerting(transformed, per_report, threshold_pct)
    transformed = alerting["df"]

    quality = report_before.merge(report_after[["regle", "nb_echecs"]], on="regle",
                                  suffixes=("_avant_nettoyage", "_apres_nettoyage"))
    outputs = {
        "01_rapport_validation": report_before,
        "02_detail_echecs_validation": details,
        "03_journal_nettoyage": log,
        "04_quarantaine": quarantine,
        "05_dataset_propre": clean_df,
        "06_rapport_qualite": quality,
        "07_dataset_transforme": transformed,
        "08_indicateurs_par_rapport": per_report,
        "09_synthese_baseline": baseline,
        "10_ecarts_controle": alerting["gaps"],
        "11_calibrage_seuil": alerting["calibration"],
        "12_alertes": alerting["alerts"],
        "13_comparaison_baseline": alerting["comparison"],
    }
    export(outputs, output_folder)
    export_alerts_excel(alerting["alerts"], Path(output_folder) / "12_alertes.xlsx")

    print("\n=========== RÉSUMÉ ===========")
    print(f"Lignes d'origine        : {len(raw)}")
    print(f"Lignes propres          : {len(clean_df)}")
    print(f"Lignes en quarantaine   : {len(quarantine)}")
    print(f"Doublons supprimés      : {n_dup}")
    print(f"Échecs de validation    : {details['id_ligne'].nunique()} lignes / {len(details)} échecs (avant nettoyage)")
    print(f"Lignes avec alerte      : {int((clean_df['alerte_temps'] | clean_df['alerte_page']).sum())} (conservées)")
    print("\nBaseline (saisie manuelle) :")
    print(baseline.to_string(index=False))

    alerts = alerting["alerts"]
    print(f"\n=========== ALERTES (seuil {threshold_pct} %) ===========")
    for source in ["manuel", "outil"]:
        a = alerts[alerts["source"] == source]
        print(f"{source:7s}: {len(a)} alertes sur {a['id_report'].nunique()} rapports "
              f"({(a['niveau'] == 'ÉLEVÉ').sum()} élevées)")
    for _, row in alerts.head(5).iterrows():
        print(f"  [{row['niveau']}] {row['message']}\n          -> {row['action']}")
    print("\nCalibrage du seuil (saisie manuelle) :")
    print(alerting["calibration"].to_string(index=False))
    print("\nComparaison avec la baseline :")
    print(alerting["comparison"].to_string(index=False))
    return outputs


if __name__ == "__main__":
    import sys
    run_pipeline(sys.argv[1] if len(sys.argv) > 1 else "data/dataset_extraction_annexes_financieres.csv")
