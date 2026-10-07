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

## Étapes

| Étape | Commande | Entrée | Sortie |
|---|---|---|---|
| 1. `ingest_merimee` | `uv run python -m lutece_pipeline.ingest_merimee` | CSV national Mérimée (data.gouv.fr) | `data/interim/merimee.parquet` |

Options de `ingest_merimee` : `--refresh` retélécharge le CSV même s'il est à
jour, `--offline` réutilise la copie locale sans accès réseau.

## Données

`data/raw`, `data/interim` et `data/processed` sont ignorés par git.

Les 13 notices de `tests/fixtures/merimee_sample.csv` sont extraites telles
quelles de la base Mérimée (ministère de la Culture, Licence Ouverte 2.0,
version du 1er octobre 2026), limitées aux colonnes lues par l'étape.

## Source Mérimée

- **Jeu de données** : « Immeubles protégés au titre des Monuments
  Historiques », ministère de la Culture, Licence Ouverte 2.0, mis à jour chaque
  semaine.
  <https://www.data.gouv.fr/datasets/immeubles-proteges-au-titre-des-monuments-historiques-2>
- **Format** : un CSV national (environ 100 Mo, 46 760 notices, 78 colonnes),
  séparateur `|`, UTF-8. Les cellules multivaluées sont séparées par `;`.
- **Téléchargement** : lien stable data.gouv.fr, copie locale dans
  `data/raw/merimee/`. L'ETag du dernier téléchargement est conservé dans
  `merimee.meta.json` ; le fichier n'est retransféré que s'il a changé.
- **Filtre** : `Departement_format_numerique == "75"`, soit 1 893 notices.

### Colonnes de `merimee.parquet`

| Colonne | Type | Colonne source | Règle |
|---|---|---|---|
| `merimee_id` | texte | `Reference` | identifiant `PA…`, unique |
| `name` | texte | `Titre_editorial_de_la_notice` | |
| `notice_type` | texte | `Typologie_du_dossier` | `protection` ou `renvoi` |
| `denominations` | liste | `Denomination_de_l_edifice` | découpée sur `;` |
| `domain` | texte | `Domaine` | |
| `address` | texte | `Adresse_forme_editoriale` | à défaut `Adresse_forme_index` |
| `arrondissement` | entier | `COG_Insee_lors_de_la_protection` | `75104` → 4 |
| `lat`, `lon` | réels | `coordonnees_au_format_WGS84` | vides si absentes ou hors de Paris |
| `protection` | texte | `Typologie_de_la_protection` | niveau le plus fort : `classé` l'emporte sur `inscrit` |
| `protection_raw` | texte | `Typologie_de_la_protection` | valeur d'origine, dont « partiellement » |
| `protection_desc` | texte | `Precision_de_la_protection` | |
| `protection_dates_raw` | texte | `Date_et_typologie_de_la_protection` | |
| `construction_century` | entier | `Format_abrege_du_siecle_de_construction` | siècle le plus ancien ; à défaut lu dans `Siecle_de_la_campagne_principale_de_construction` |
| `earliest_dated_year` | entier | `Datation_de_l_edifice` | année la plus ancienne citée ; elle peut dater une campagne de travaux postérieure à la construction |
| `period_raw` | texte | `Siecle_de_la_campagne_principale_de_construction` | |
| `authors` | liste | `Auteur_de_l_edifice` | découpée sur `;`, rôle conservé |
| `architects` | liste | `Auteur_de_l_edifice` | auteurs dont le rôle contient « architecte » ou « maître de l'œuvre », sans le rôle ; noms non reformatés |
| `history_raw` | texte | `Historique` | |
| `description_raw` | texte | `Description_de_l_edifice` | |
| `owner_status` | texte | `Statut_juridique_de_l_edifice` | |
| `source_updated_at` | date | `Date_de_la_derniere_mise_a_jour` | |

### Constats sur les notices parisiennes (version du 1er octobre 2026)

- 1 893 notices : 1 414 inscrites, 464 classées, 15 sans protection renseignée
  (dont 5 notices de renvoi).
- Coordonnées : 3 notices sans coordonnées, et 1 point aberrant écarté
  (`PA75110005`, « 48.00000000000001,2 »).
- 53 notices sans adresse, 255 sans siècle ni année, 1 149 sans texte
  historique, 1 199 sans architecte identifié.
- 682 notices portent un nom générique (« Immeuble », « Immeubles », « Maison »,
  « Hôtel », « Boutique »).
- Pour 15 notices, `earliest_dated_year` est postérieure d'au moins deux siècles
  à `construction_century` (palais du Louvre : 12e siècle, année 1808).

## Écarts constatés avec SPEC §5.1

- Le portail `data.culture.gouv.fr` redirige vers `culture.data.gouv.fr` et son
  ancienne API ne répond plus. La base est désormais diffusée sur data.gouv.fr,
  sous forme d'un fichier national à filtrer localement.
- Le SPEC annonçait des coordonnées « parfois » présentes : 1 890 notices
  parisiennes sur 1 893 en ont.
