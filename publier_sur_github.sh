#!/bin/bash
# Publie le projet sur GitHub. Prérequis : git et GitHub CLI (brew install gh), puis `gh auth login`.
set -e
cd "$(dirname "$0")"
[ -d .git ] || { git init -b main; git add .; git commit -m "Pipeline d'extraction et de contrôle des notes annexes financières"; }
gh repo create extraction-annexes-financieres --private --source=. --remote=origin --push
echo "Projet publié : $(gh repo view --json url -q .url)"
