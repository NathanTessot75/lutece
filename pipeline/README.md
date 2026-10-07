# Pipeline de données Lutèce

Pipeline Python hors ligne qui construit la base patrimoniale (SPEC §5).
Une étape = un module dans `src/lutece_pipeline/`, rejouable indépendamment.

## Commandes

À lancer depuis `pipeline/` :

```bash
uv sync                 # installer l'environnement (Python 3.13)
uv run pytest           # tests
uv run ruff check .     # lint (annotations de type obligatoires)
uv run ruff format .    # formatage
```

## Données

`data/raw`, `data/interim` et `data/processed` sont ignorés par git.

## Écarts constatés avec les sources

Aucun pour l'instant. Tout écart de format (noms de champs, pagination) par
rapport à SPEC §5.1 est consigné ici.
