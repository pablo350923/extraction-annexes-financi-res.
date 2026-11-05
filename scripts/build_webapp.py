"""Construit webapp_controle_annexes.html : la page autonome (sans installation).
Elle contient les résultats du jeu de démonstration et le code de pipeline.py,
exécuté dans le navigateur (Pyodide) quand on importe un autre fichier.
Usage : python scripts/build_webapp.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pipeline  # noqa: E402

data = pipeline.dashboard_data(ROOT / "data" / "dataset_extraction_annexes_financieres.csv")
template = (ROOT / "scripts" / "template_app.html").read_text(encoding="utf-8")
source = (ROOT / "pipeline.py").read_text(encoding="utf-8")
html = (template.replace("__DATA__", json.dumps(data, ensure_ascii=False))
                .replace("__PIPELINE__", json.dumps(source, ensure_ascii=False).replace("</", "<\\/")))
(ROOT / "webapp_controle_annexes.html").write_text(html, encoding="utf-8")
print("webapp_controle_annexes.html générée")
