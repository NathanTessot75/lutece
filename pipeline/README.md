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
| 2. `ingest_wikidata` | `uv run python -m lutece_pipeline.ingest_wikidata` | `merimee.parquet`, service de requêtes Wikidata | `data/interim/wikidata_items.parquet`, `data/interim/wikidata_merimee_links.parquet` |

Options :

- `ingest_merimee --refresh` retélécharge le CSV même s'il est à jour ;
  `--offline` réutilise la copie locale sans accès réseau.
- `ingest_wikidata --offline` rejoue l'étape à partir des dernières réponses
  enregistrées dans `data/raw/wikidata/snapshot.json`.

Les fichiers Parquet se lisent avec `pd.read_parquet(chemin)`. Ajouter
`dtype_backend="pyarrow"` conserve les entiers avec valeurs manquantes au lieu
de les convertir en réels.

## Données

`data/raw`, `data/interim` et `data/processed` sont ignorés par git.

Les 13 notices de `tests/fixtures/merimee_sample.csv` sont extraites telles
quelles de la base Mérimée (ministère de la Culture, Licence Ouverte 2.0,
version du 1er octobre 2026), limitées aux colonnes lues par l'étape.
`tests/fixtures/wikidata_snapshot.json` contient les réponses réelles de
Wikidata (CC0) pour ces mêmes notices, enregistrées le 7 octobre 2026.

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

## Source Wikidata

- **Service** : <https://query.wikidata.org/sparql>, données sous licence CC0.
  Le client s'identifie par un en-tête `User-Agent` avec contact, comme le
  demande Wikimedia.
- **Jointure** : exacte, sur la propriété P380 (identifiant Mérimée), à partir
  des identifiants de `merimee.parquet`, par lots de 300.
- **Détails** : une seconde requête lit les propriétés des éléments trouvés,
  par lots de 250. Les propriétés à plusieurs valeurs sont concaténées par le
  service puis départagées ici, toujours de la même façon (première valeur dans
  l'ordre alphabétique, ou premier point situé dans Paris).
- **Robustesse** : le service renvoie parfois des erreurs 429 ou 5xx pendant
  quelques secondes ; chaque requête est retentée jusqu'à cinq fois.

### Colonnes de `wikidata_merimee_links.parquet`

Une ligne par paire `merimee_id` / `qid`. La relation est
plusieurs-à-plusieurs.

### Colonnes de `wikidata_items.parquet`

| Colonne | Type | Propriété | Règle |
|---|---|---|---|
| `qid` | texte | | identifiant de l'élément, unique |
| `label_fr` | texte | libellé | en français |
| `lat`, `lon` | réels | P625 | premier point situé dans Paris, vides sinon |
| `commons_category` | texte | P373 | |
| `frwiki_title`, `frwiki_url` | texte | lien de site | article de Wikipédia en français |
| `image_file` | texte | P18 | nom du fichier sur Commons |
| `inception_year` | entier | P571 | année la plus ancienne |
| `architects` | liste | P84 | libellés en français |
| `instance_of` | liste | P31 | libellés en français (« hôtel particulier », « église »…) |
| `sitelinks` | entier | | nombre de liens vers les projets Wikimedia |

### Constats (réponses du 7 octobre 2026)

- 1 885 notices sur 1 893 ont au moins un élément Wikidata ; 8 n'en ont pas
  (`PA00085987`, `PA00088785`, `PA75080012`, `PA75090010`, `PA75140018`,
  `PA75170008`, `PA75180003`, `PA75180005`).
- 2 004 liens vers 1 990 éléments. 59 notices ont plusieurs éléments, jusqu'à
  19 pour le cimetière du Père-Lachaise (le cimetière et ses tombes) ; 13
  éléments sont rattachés à plusieurs notices.
- Par élément : 3 sans coordonnées dans Paris, 75 sans catégorie Commons, 59
  sans image, 1 081 sans article Wikipédia en français, 1 498 sans architecte,
  1 483 sans date de création.
- Les points Wikidata et Mérimée d'une même paire sont distants de 10 m en
  médiane et de 66 m au 9e décile ; 61 paires sur 1 997 dépassent 200 m.
- Certains liens sont faux côté Wikidata : `PA00086620` (immeuble du 21 rue
  Boissonnade, 14e) y est porté par l'hôtel du 28 rue Geoffroy-l'Asnier (4e).
  L'étape `resolve_entities` devra contrôler la distance entre les sources.

## Écarts constatés avec le SPEC

- §5.1 : le portail `data.culture.gouv.fr` redirige vers
  `culture.data.gouv.fr` et son ancienne API ne répond plus. La base est
  désormais diffusée sur data.gouv.fr, sous forme d'un fichier national à
  filtrer localement.
- §5.1 : le SPEC annonçait des coordonnées « parfois » présentes ; 1 890
  notices parisiennes sur 1 893 en ont.
- §5.2, étape 2 : la requête géographique proposée (`wdt:P131* wd:Q90`) met
  une vingtaine de secondes et ramène 2 019 identifiants, dont une partie hors
  de notre liste. Elle est remplacée par une jointure exacte sur nos
  identifiants.
- §4 : `SPARQLWrapper` n'est pas utilisé, `httpx` suffit pour interroger le
  service.
