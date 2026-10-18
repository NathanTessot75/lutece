# Lutèce — conventions pour Claude Code

Référence complète : `SPEC.md` (fait foi en cas de contradiction).

## Méthode
- Travailler phase par phase (SPEC §9) ; une phase ne démarre qu'après validation de la précédente.
- Avant de coder : plan court (fichiers, dépendances, choix techniques), puis attendre la validation de Nathan.
- Un sujet par modification, pas de refactor non demandé.
- Demander avant d'ajouter une dépendance non listée dans SPEC.md.
- Vérifier les versions des librairies à l'installation ; signaler toute information du SPEC fausse ou datée au lieu de la contourner.

## Conventions
- Doc et UI en français ; code, commentaires et commits en anglais.
- App : TypeScript `strict`. `ios/` et `android/` sont générés par prebuild et ignorés par git : la config native passe par `app.json` et les config plugins.
- Pipeline : Python typé, une étape = un module dans `pipeline/src/lutece_pipeline/`, chaque étape rejouable.
- Schéma de base : uniquement via `supabase/migrations/`.
- Jamais dans git : `pipeline/data/` (hors petits échantillons), photos du jeu de test, secrets (`.env*`).

## Commandes
| Dossier | Commande | Rôle |
|---|---|---|
| `apps/mobile` | `npx expo start` | serveur de dev (dev build) |
| `apps/mobile` | `npx expo run:ios --device` | compiler et installer sur l'iPhone |
| `apps/mobile` | `npx tsc --noEmit` · `npm run lint` · `npm test` | types · lint · tests |
| `pipeline` | `uv sync` | installer l'environnement |
| `pipeline` | `uv run ruff check .` · `uv run ruff format .` · `uv run pytest` | lint · format · tests |
| `pipeline` | `uv run python -m lutece_pipeline.load_postgres` | charger les monuments dans la base locale |
| `pipeline` | `uv run python -m lutece_pipeline.selection --offline` | choisir les monuments que l'app montre (sans `--offline` : interroge Wikidata) |
| `pipeline` | `uv run python -m lutece_pipeline.landmark_places --offline` | reconstruire les lieux non protégés gardés dans `review/landmarks.csv` |
| `pipeline` | `uv run python -m lutece_pipeline.evaluate_retrieval` | mesurer la reconnaissance d'image (après `fetch_reference_photos`, `export_model`, `embed_references` et `check_reference_photos`) |
| `pipeline` | `uv run python -m lutece_pipeline.pull_field_samples` | copier les photos du mode collecte depuis l'iPhone (déverrouillé) dans `eval/testset/` |
| `pipeline` | `uv run python -m lutece_pipeline.rarity` | calculer la rareté des lieux de l'app (avant `export_bundle`) |
| `pipeline` | `uv run python -m lutece_pipeline.series` | ranger les lieux de l'app en séries d'après `review/series.csv` (avant `export_bundle`) |
| `pipeline` | `uv run python -m lutece_pipeline.export_bundle` | régénérer le fichier des monuments embarqué dans l'app |
| racine | `supabase start` · `supabase stop` | pile locale (runtime de conteneurs requis) |
| racine | `supabase migration up` | appliquer les nouvelles migrations sans vider la base |
| racine | `supabase db reset` | rejouer migrations et seed (vide la base) |
| racine | `supabase migration new <name>` | nouvelle migration |
| racine | `supabase test db` | tests des droits de la base (pgTAP) |
| racine | `supabase db push` | appliquer les migrations au projet hébergé |
