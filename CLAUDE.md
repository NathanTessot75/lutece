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
| `apps/mobile` | `npx tsc --noEmit` · `npm run lint` | types · lint |
| `pipeline` | `uv sync` | installer l'environnement |
| `pipeline` | `uv run ruff check .` · `uv run ruff format .` · `uv run pytest` | lint · format · tests |
| racine | `supabase start` · `supabase stop` | pile locale (runtime de conteneurs requis) |
| racine | `supabase db reset` | rejouer migrations et seed |
| racine | `supabase migration new <name>` | nouvelle migration |
