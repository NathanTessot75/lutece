# Lutèce

Une application iPhone qui fait de Paris un terrain de jeu : on se promène, on
vise un monument avec l'appareil photo et on le **capture** pour l'ajouter à sa
collection et découvrir son histoire. Les lieux peu connus rapportent plus que
les monuments célèbres.

C'est aussi un projet de data science : construire une base patrimoniale
unifiée à partir de sources ouvertes (base Mérimée, Wikidata, OpenStreetMap,
Wikipédia, Wikimedia Commons) et évaluer rigoureusement la reconnaissance des
monuments sur une photo.

## Ce que fait l'application aujourd'hui

- **394 lieux sur une carte hors ligne** : 323 monuments historiques parmi les
  plus connus de Paris et 71 lieux célèbres non protégés.
- **La capture** combine la position GPS, la direction de la boussole et la
  photo. Un modèle de vision (DINOv2, 22,5 Mo) compare la photo aux photos de
  référence du lieu, sur le téléphone, sans réseau.
- **Le jeu** : des points selon la rareté du lieu, la progression par
  arrondissement et par série (21 séries : ponts, passages couverts…), 41
  badges, un classement en ligne dont le serveur vérifie les captures.
- **Les fiches** : l'histoire de chaque lieu, rédigée par un modèle de langage
  à partir de la notice Mérimée et de l'article Wikipédia, avec ses sources.
- **La contribution** : un joueur qui le veut envoie ses photos pour mesurer et
  améliorer la reconnaissance.

## Le dépôt

| Dossier | Contenu |
|---|---|
| `apps/mobile/` | l'application (Expo, React Native, TypeScript) |
| `pipeline/` | le pipeline de données en Python : une étape par module, rejouable |
| `supabase/` | le serveur : schéma, règles d'accès et leurs tests |
| `eval/` | le jeu de test terrain (métadonnées ; les photos restent hors du dépôt) |
| `docs/rapport/` | le rapport de qualité de la base patrimoniale |
| `SPEC.md` | le cahier des charges du projet |

La méthode est détaillée, étape par étape et chiffres à l'appui, dans
[`pipeline/README.md`](pipeline/README.md) ; le serveur dans
[`supabase/README.md`](supabase/README.md).

## Quelques chiffres

| | |
|---|---|
| Notices Mérimée à Paris | 1 878 |
| Lieux montrés par l'app | 394 |
| Photos de référence gardées | 4 335 |
| Bon lieu en premier (photos de Commons) | 89,8 %, contre 33,6 % au hasard |
| Photos refusées alors qu'elles montrent leur lieu | 4,1 % |

Ces mesures viennent de photos de Wikimedia Commons, plus nettes que celles
d'un téléphone dans la rue ; le jeu de test terrain dira ce que vaut la
reconnaissance en conditions réelles.

## Essayer

**L'application** demande un Mac avec Xcode et un iPhone (un compte Apple
gratuit suffit pour l'installer sur son propre téléphone) :

```bash
cd apps/mobile
npm install
npx expo run:ios --device
```

Elle fonctionne hors ligne : le fichier des lieux et le modèle sont dans le
dépôt. La contribution des photos et le classement demandent un projet
Supabase, dont l'adresse et la clé publique vont dans `apps/mobile/.env`
(modèle : `.env.example`).

**Le pipeline** demande Python 3.13 et [uv](https://docs.astral.sh/uv/) :

```bash
cd pipeline
uv sync
uv run pytest
```

Les étapes se lancent une à une (`uv run python -m lutece_pipeline.<étape>`) ;
leur liste, leurs entrées et leurs sorties sont dans `pipeline/README.md`. Les
données téléchargées des sources ouvertes restent dans `pipeline/data/`, hors
du dépôt.

**Le serveur** se teste en local avec la CLI Supabase et Docker :

```bash
supabase start
supabase test db
```

## Licences des données

Base Mérimée : Licence Ouverte (Etalab). OpenStreetMap : ODbL. Wikipédia :
CC BY-SA 4.0, comme les fiches qui en dérivent. Wikimedia Commons : la licence
de chaque photo, enregistrée avec son auteur et affichée dans l'app.
