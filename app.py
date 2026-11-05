"""
Application web – Contrôle des données extraites des notes annexes financières.
Lancer :  streamlit run app.py
"""
import io
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

import pipeline as pl

DEMO_FILE = Path(__file__).parent / "data" / "dataset_extraction_annexes_financieres.csv"
LEVEL_COLORS = {"ÉLEVÉ": "background-color: #F8CBAD", "MOYEN": "background-color: #FFE699"}

st.set_page_config(page_title="Contrôle des annexes financières", page_icon="📊", layout="wide")


@st.cache_data(show_spinner="Exécution du pipeline…")
def run(file_bytes, suffix, threshold):
    """Écrit le fichier dans un dossier temporaire et lance le pipeline complet."""
    folder = Path(tempfile.mkdtemp())
    source = folder / f"source{suffix}"
    source.write_bytes(file_bytes)
    outputs = pl.run_pipeline(source, output_folder=folder / "outputs", threshold_pct=threshold)
    excel = (folder / "outputs" / "12_alertes.xlsx").read_bytes()
    return outputs, excel


def zip_outputs(outputs):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, table in outputs.items():
            z.writestr(f"{name}.csv", table.to_csv(index=False).encode("utf-8-sig"))
    return buffer.getvalue()


# ---------------- Barre latérale : paramètres ----------------
st.sidebar.header("Paramètres")
uploaded = st.sidebar.file_uploader("Jeu de données (CSV ou Excel)", type=["csv", "xlsx"])
threshold = st.sidebar.select_slider(
    "Seuil d'alerte (écart de contrôle, %)", options=[4.0, 2.0, 1.0, 0.5, 0.1], value=pl.THRESHOLD_PCT,
    help="4 % = valeur du modèle du cours ; 0,1 % = seuil retenu après calibrage")
st.sidebar.caption("Sans fichier, l'application utilise le jeu de données synthétique du projet.")

if uploaded is not None:
    file_bytes, suffix, source_name = uploaded.getvalue(), Path(uploaded.name).suffix, uploaded.name
else:
    file_bytes, suffix, source_name = DEMO_FILE.read_bytes(), ".csv", DEMO_FILE.name

outputs, alerts_excel = run(file_bytes, suffix, threshold)
alerts = outputs["12_alertes"]
comparison = outputs["13_comparaison_baseline"].set_index("scenario")

# ---------------- En-tête et indicateurs ----------------
st.title("📊 Contrôle des données extraites des notes annexes")
st.caption(f"Source : **{source_name}** · Workflow : rapports → extraction → écart de contrôle → seuil {threshold} % → alerte")

manual_alerts = alerts[alerts["source"] == "manuel"]
base, with_alert = comparison.iloc[0], comparison.iloc[1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Rapports analysés", outputs["08_indicateurs_par_rapport"]["id_report"].nunique())
c2.metric("Alertes (saisie manuelle)", len(manual_alerts),
          f"{(manual_alerts['niveau'] == 'ÉLEVÉ').sum()} élevées", delta_color="off")
c3.metric("Erreur manuelle résiduelle", f"{with_alert['taux_erreur_residuel_pct']:.2f} %",
          f"{with_alert['taux_erreur_residuel_pct'] - base['taux_erreur_residuel_pct']:.2f} pts vs baseline",
          delta_color="inverse")
c4.metric("Temps manuel par rapport", f"{base['temps_par_rapport_min']:.1f} min")

tab_alerts, tab_threshold, tab_baseline, tab_quality, tab_data = st.tabs(
    ["🚨 Alertes", "🎚️ Calibrage du seuil", "⚖️ Comparaison baseline", "✅ Qualité des données", "🗂️ Données"])

with tab_alerts:
    col_a, col_b = st.columns(2)
    sources = col_a.multiselect("Source", ["manuel", "outil"], default=["manuel", "outil"])
    levels = col_b.multiselect("Niveau", ["ÉLEVÉ", "MOYEN"], default=["ÉLEVÉ", "MOYEN"])
    shown = alerts[alerts["source"].isin(sources) & alerts["niveau"].isin(levels)]
    if shown.empty:
        st.success("Aucune alerte pour cette sélection.")
    else:
        table = shown[["niveau", "source", "id_report", "message", "action"]]
        st.dataframe(table.style.apply(lambda r: [LEVEL_COLORS[r["niveau"]]] * len(r), axis=1),
                     width="stretch", hide_index=True, height=480)
    st.download_button("⬇️ Télécharger les alertes (Excel)", alerts_excel, "alertes.xlsx")

with tab_threshold:
    st.markdown("Chaque seuil est évalué sur la saisie manuelle grâce au label `erreur_saisie` (vérité terrain).")
    calibration = outputs["11_calibrage_seuil"]
    st.bar_chart(calibration.assign(seuil=calibration["seuil_pct"].astype(str) + " %")
                 .set_index("seuil")[["vraies_alertes", "erreurs_ratees"]], stack=True)
    st.dataframe(calibration, width="stretch", hide_index=True)

with tab_baseline:
    st.markdown("**Question X/Y/Z** : l'outil + l'alerte (X) réduisent-ils le temps et les erreurs (Y) "
                "par rapport à la saisie manuelle dans Excel (Z) ?")
    st.dataframe(outputs["13_comparaison_baseline"], width="stretch", hide_index=True)
    st.markdown("**Baseline par type de tableau**")
    st.dataframe(outputs["09_synthese_baseline"], width="stretch", hide_index=True)
    st.caption("Hypothèse : revérifier un champ signalé prend le temps manuel moyen d'un champ.")

with tab_quality:
    st.markdown("**Règles du Data Contract – avant et après nettoyage**")
    st.dataframe(outputs["06_rapport_qualite"].drop(columns="lignes_concernees"), width="stretch", hide_index=True)
    st.markdown("**Journal de nettoyage**")
    st.dataframe(outputs["03_journal_nettoyage"], width="stretch", hide_index=True)
    st.markdown(f"**Quarantaine** ({len(outputs['04_quarantaine'])} lignes)")
    if outputs["04_quarantaine"].empty:
        st.info("Aucune ligne en quarantaine : tous les défauts étaient corrigeables.")
    else:
        st.dataframe(outputs["04_quarantaine"], width="stretch", hide_index=True)

with tab_data:
    st.dataframe(outputs["07_dataset_transforme"], width="stretch", hide_index=True, height=480)
    st.download_button("⬇️ Télécharger toutes les sorties (ZIP de CSV)", zip_outputs(outputs), "sorties_pipeline.zip")
