## Ce que change cette demande

<!-- Une ou deux phrases ; le ticket lié s'il existe. -->

## Vérifications

- [ ] `python -m pytest -q` passe (avec `QT_QPA_PLATFORM=offscreen`)
- [ ] `ruff check .` passe
- [ ] Projets de référence : aucune différence, ou `UPDATE_GOLDEN=1` lancé et chaque ligne changée de `tests/golden/` expliquée ci-dessous
- [ ] Niveau de prise en charge des fiches touchées à jour (`docs/prise-en-charge.md` régénéré)
- [ ] Ligne ajoutée au CHANGELOG
- [ ] Pas de changement du format du fichier projet, ou `docs/format.md` et une migration à jour

## Différences dans les fichiers générés

<!-- Pourquoi chaque changement de tests/golden/ est voulu. -->
