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
| 3. `ingest_osm` | `uv run python -m lutece_pipeline.ingest_osm` | `merimee.parquet`, `wikidata_merimee_links.parquet`, API Overpass | `data/interim/osm_objects.parquet`, `data/interim/osm_merimee_links.parquet` |
| 4. `resolve_entities` | `uv run python -m lutece_pipeline.resolve_entities` | les sorties des étapes 1 à 3, `review/entity_decisions.csv` | `data/interim/entities.parquet`, `data/interim/entity_links.parquet`, `data/interim/entities_to_review.csv` |
| 5a. `nearby_buildings` | `uv run python -m lutece_pipeline.nearby_buildings` | les sorties des étapes 1 à 4, API Overpass | `data/interim/nearby_buildings.parquet`, `data/interim/nearby_buildings_evaluation.csv` |
| 5b. `geometry` | `uv run python -m lutece_pipeline.geometry` | les sorties des étapes 1 à 5a, `review/geometry_overrides.csv` | `data/interim/geometries.parquet`, `data/interim/geometries_to_review.csv` |
| 6. `visibility` | `uv run python -m lutece_pipeline.visibility` | `merimee.parquet`, `review/visibility_overrides.csv`, `review/visibility_labels.csv` | `data/interim/visibility.parquet`, `data/interim/visibility_to_review.csv`, `data/interim/visibility_evaluation.csv` |
| 7. `ingest_commons` | `uv run python -m lutece_pipeline.ingest_commons` | `merimee.parquet`, `entities.parquet`, `wikidata_items.parquet`, API Commons, `review/commons_labels.csv` | `data/interim/commons_files.parquet`, `data/interim/commons_categories.parquet`, `data/interim/commons_evaluation.csv` |
| — `selection` | `uv run python -m lutece_pipeline.selection` | `merimee.parquet`, `entities.parquet`, `wikidata_items.parquet`, `visibility.parquet`, Wikidata, statistiques de Wikipédia, `review/selection_overrides.csv` | `data/interim/selection.parquet`, `data/interim/selection_ranking.csv` |
| 11. `load_postgres` | `uv run python -m lutece_pipeline.load_postgres` | les sorties des étapes 1 à 7, une base Postgres | tables `monuments` et `reference_images` |
| 11. `export_bundle` | `uv run python -m lutece_pipeline.export_bundle` | les sorties des étapes 1 à 7, `selection.parquet`, `review/capture_reach.csv` | `apps/mobile/assets/data/lutece.db`, `apps/mobile/assets/data/bundle.json` |
| 12. `quality_report` | `uv run python -m lutece_pipeline.quality_report` | les sorties des étapes 1 à 7 | `data/processed/monuments_quality.parquet`, `data/processed/quality_problems.csv`, `docs/rapport/qualite-donnees.md` |

Options :

- `ingest_merimee --refresh` retélécharge le CSV même s'il est à jour ;
  `--offline` réutilise la copie locale sans accès réseau.
- `ingest_wikidata --offline` rejoue l'étape à partir des dernières réponses
  enregistrées dans `data/raw/wikidata/snapshot.json`.
- `ingest_osm --offline` fait de même à partir de `data/raw/osm/snapshot.json`.
- `nearby_buildings --offline` fait de même à partir de
  `data/raw/osm/nearby_buildings.json`. En ligne, chaque lot obtenu est
  sauvegardé : après un échec du serveur, relancer la commande reprend là où
  elle s'était arrêtée.
- `ingest_commons` ne redemande à Commons que ce qui manque dans
  `data/raw/commons/`. `--offline` n'utilise que ces réponses enregistrées ;
  `--refresh` les oublie et redemande tout.
- `load_postgres` charge la base locale de Supabase, sauf si la variable
  d'environnement `LUTECE_DATABASE_URL` désigne une autre base.
  `--data-version N` fixe le numéro de version enregistré avec chaque monument.

Les fichiers Parquet se lisent avec `pd.read_parquet(chemin)`. Ajouter
`dtype_backend="pyarrow"` conserve les entiers avec valeurs manquantes au lieu
de les convertir en réels. `osm_objects.parquet` contient des géométries : le
lire avec `geopandas.read_parquet(chemin)`.

## Données

`data/raw`, `data/interim` et `data/processed` sont ignorés par git.

Les 13 notices de `tests/fixtures/merimee_sample.csv` sont extraites telles
quelles de la base Mérimée (ministère de la Culture, Licence Ouverte 2.0,
version du 1er octobre 2026), limitées aux colonnes lues par l'étape.
`tests/fixtures/wikidata_snapshot.json` contient les réponses réelles de
Wikidata (CC0) pour ces mêmes notices, enregistrées le 7 octobre 2026.
`tests/fixtures/osm_snapshot.json` contient les 12 objets OpenStreetMap liés à
ces notices (© les contributeurs d'OpenStreetMap, licence ODbL), enregistrés le
même jour. `tests/fixtures/osm_nearby_snapshot.json` contient, sous la même
licence, les 37 bâtiments OpenStreetMap situés à moins de 30 m de cinq de ces
notices. `tests/fixtures/commons_snapshot.json` contient un extrait des
réponses de Wikimedia Commons pour ces notices, enregistrées le 8 octobre
2026 : 6 fichiers au plus par catégorie, décrits par leur auteur et leur
licence ; aucune image n'y figure.

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
| `protection_lifted` | booléen | `Observations`, `Precision_de_la_protection` | vrai pour un dossier de protection sans niveau de protection dont les textes mentionnent une radiation, une annulation ou une abrogation |
| `observations` | texte | `Observations` | |
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

- 1 893 notices : 1 414 inscrites, 464 classées, 15 sans protection renseignée.
  Ces 15 ne sont pas des monuments à capturer : 10 ont vu leur protection
  radiée, abrogée ou annulée (`protection_lifted`, le détail est dans
  `observations` ou `protection_desc`) et 5 sont des notices de renvoi vers une
  autre notice. Le jeu porte donc sur 1 878 notices au plus.
- 221 notices encore protégées mentionnent aussi une abrogation dans leurs
  observations : il s'agit d'une ancienne protection remplacée par l'actuelle.
  Elles ne sont pas marquées `protection_lifted`.
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

## Source OpenStreetMap

- **Service** : API Overpass, <https://overpass-api.de/api/interpreter>.
  Données © les contributeurs d'OpenStreetMap, licence ODbL : attribution
  obligatoire, et partage à l'identique de la base dérivée.
- **Deux clés de rapprochement** : l'étiquette `ref:mhs` (identifiant Mérimée)
  et l'étiquette `wikidata`, quand elle désigne l'un des éléments trouvés par
  `ingest_wikidata`.
- **Requêtes** : les objets portant `ref:mhs` à Paris, avec leur géométrie ;
  puis la liste des objets portant `wikidata` à Paris, sans géométrie (environ
  17 000) ; enfin la géométrie des seuls objets retenus, par lots de 400
  identifiants.
- **Robustesse** : mêmes reprises que pour Wikidata. Overpass signale aussi
  certains échecs dans une réponse 200, par un champ `remark` : l'étape les
  traite comme des erreurs.

### Géométries

| Objet OSM | Géométrie produite |
|---|---|
| nœud | point |
| chemin fermé | polygone, sauf route ou clôture non marquée `area=yes` |
| chemin ouvert | ligne |
| relation `multipolygon` | anneaux recousus quel que soit l'ordre des chemins, trous retirés |
| autre relation (`site`, `associatedStreet`, `public_transport`…) | union des chemins fermés, chacun comptant pour une surface ; à défaut les lignes, puis les nœuds |

Les géométries invalides sont réparées. Une relation `associatedStreet`
regroupe une rue et ses immeubles : elle décrit le voisinage d'un monument
plutôt que le monument. La colonne `relation_type` permet de l'écarter.

### Colonnes de `osm_objects.parquet`

GeoParquet en WGS84 (EPSG:4326), une ligne par objet lié à au moins une notice.

| Colonne | Type | Contenu |
|---|---|---|
| `osm_type` | texte | `node`, `way` ou `relation` |
| `osm_id` | entier | unique pour un type donné |
| `relation_type` | texte | étiquette `type` des relations, vide sinon |
| `name`, `ref_mhs`, `wikidata`, `building` | texte | étiquettes du même nom |
| `tags` | texte | toutes les étiquettes, en JSON |
| `geometry` | géométrie | voir ci-dessus |

### Colonnes de `osm_merimee_links.parquet`

Une ligne par paire notice / objet : `merimee_id`, `osm_type`, `osm_id`, puis
`via_ref_mhs` et `via_wikidata`, qui indiquent quelle étiquette désigne la
notice. La relation est plusieurs-à-plusieurs.

### Constats (réponses du 7 octobre 2026)

- 2 154 objets retenus : 494 nœuds, 1 256 chemins, 404 relations (335
  `multipolygon`, 44 `associatedStreet`, 10 `site`, 10 `public_transport`,
  4 `street`, 1 `waterway`).
- 1 705 notices sur 1 893 ont au moins un objet ; 188 n'en ont aucun. 799 sont
  atteintes par `ref:mhs`, 1 667 par `wikidata`, 761 par les deux.
- 1 376 notices ont une emprise : un chemin ou une relation `multipolygon` ou
  `site` de surface non nulle. Surface médiane 428 m², de 110 m² (1er décile) à
  2 707 m² (9e décile).
- 261 notices ont plusieurs objets, jusqu'à 17 ; 15 objets désignent plusieurs
  notices.
- Le point Mérimée est à 0 m de la géométrie OSM en médiane (il tombe dedans)
  et à 48 m au 9e décile ; 99 paires sur 2 168 dépassent 100 m, 19 dépassent
  500 m.

## Rapprochement des entités

En version 1, un monument est exactement une notice Mérimée. L'étape
`resolve_entities` ne fait aucun appel réseau : elle contrôle les liens trouvés
par les étapes 2 et 3, puis retient pour chaque notice un élément Wikidata
principal et une emprise OSM principale.

### Règles

Chaque paire notice / objet est mesurée :

- `distance_m` : distance en mètres (projection Lambert-93) entre le point
  Mérimée et le point Wikidata ou la géométrie OSM ; 0 si le point est dedans.
- `name_similarity` : score de 0 à 100 calculé par `rapidfuzz`
  (`token_sort_ratio`) sur les noms sans accents, ponctuation ni petits mots.
  Un nom simplement contenu dans l'autre ne score pas haut : « Place Vendôme »
  ne doit pas ressembler à chacun des hôtels de la place.
- `address_match` : vrai si le nom de l'objet reprend une adresse de la notice
  avec son numéro, comme « immeuble, 5 rue de Condé ».

Une paire est `confirmed` si l'une de ces conditions est remplie, `doubtful`
sinon :

| Condition | Seuil |
|---|---|
| objet proche | 100 m pour Wikidata, 50 m pour OSM |
| même nom | score d'au moins 90 |
| nom reprenant l'adresse | `address_match` |

L'objet principal d'une notice est le meilleur candidat non rejeté :

- **Wikidata** : confirmé avant douteux, puis nom le plus proche, distance la
  plus courte, plus grand nombre de liens de site.
- **OSM** : seules les emprises sont candidates (chemin, ou relation
  `multipolygon` ou `site`, de surface non nulle). Confirmée avant douteuse,
  puis étiquette `ref:mhs`, distance la plus courte, plus grande surface.

### Revue manuelle

`data/interim/entities_to_review.csv` liste ce qui mérite un regard humain : les
notices dont l'objet principal est douteux, et celles sans élément Wikidata.
Chaque ligne donne les noms, la distance et les liens vers la notice (POP),
Wikidata ou OpenStreetMap.

Les décisions sont consignées dans `review/entity_decisions.csv`, versionné,
et s'appliquent à l'exécution suivante. Colonnes : `merimee_id`, `source`
(`wikidata` ou `osm`), `entity_id` (`Q…` ou `way/123`), `decision`, `note`.

| Décision | Effet |
|---|---|
| `accept` | la paire est confirmée malgré les règles |
| `reject` | la paire est écartée |
| `primary` | la paire est confirmée et devient l'objet principal |

Une décision qui ne correspond plus à aucune paire est signalée dans le journal.

### Sorties

- `entity_links.parquet` : une ligne par paire, avec `merimee_id`, `source`,
  `entity_id`, `entity_name`, les trois mesures, `via_ref_mhs`,
  `via_wikidata`, `is_footprint` et `area_m2` (OSM seulement), `status`
  (`confirmed`, `doubtful` ou `rejected`), `reviewed` et `is_primary`.
- `entities.parquet` : une ligne par notice, avec `wikidata_qid`,
  `wikidata_status`, `wikidata_count`, `osm_footprint`, `osm_status`,
  `osm_footprint_count` et `osm_object_count`. Les compteurs excluent les
  paires rejetées.

### Constats (7 octobre 2026)

- 4 174 paires : 2 004 avec Wikidata, 2 170 avec OSM.
- Avant revue : élément principal confirmé pour 1 849 notices, douteux pour 36,
  absent pour 8 ; emprise principale confirmée pour 1 354 notices, douteuse
  pour 22, absente pour 517.
- Revue : 68 décisions (55 `accept`, 5 `reject`, 8 `primary`). Les écarts de
  position viennent surtout de sites étendus (Louvre, Luxembourg), d'entourages
  de métro et de points mal placés dans l'une des sources.
- Après revue : 1 882 notices ont un élément Wikidata confirmé et 11 n'en ont
  pas ; 1 374 ont une emprise confirmée, 1 une emprise douteuse et 518 aucune.
- 217 paires secondaires restent douteuses ; elles ne sont pas utilisées.
- Deux monuments ont été déplacés : l'usine élévatrice des eaux (`PA00086588`),
  aujourd'hui au parc de la Villette, et l'entourage Guimard de l'ancienne
  station Barbès-Rochechouart (`PA00086750`), aujourd'hui avenue Secrétan. Pour
  le premier, le point Mérimée indique encore l'ancienne adresse.

## Bâtiments autour

Beaucoup d'immeubles protégés ne portent aucune étiquette OSM qui les relie à
leur notice. L'étape `nearby_buildings` leur cherche une emprise : le bâtiment
OSM dans lequel tombe leur point de référence.

### Règle

- **Notices visées** : les monuments protégés dont la dénomination principale
  désigne un bâtiment et qui n'ont ni emprise ni ligne OSM. Une liste de 37
  dénominations (`NOT_A_BUILDING` : station de métro, fontaine, tombeau, pont,
  passage couvert, jardin, cimetière, grand ensemble…) écarte les petits
  objets, les ouvrages linéaires, les espaces ouverts et les ensembles.
- **Recherche** : les bâtiments OSM (`building=*`) à moins de 30 m du point,
  demandés à Overpass par lots de 30 points.
- **Choix** : le bâtiment qui contient le point, le plus petit s'il y en a
  plusieurs. Si le point est dehors, le bâtiment le plus proche à moins de 15 m
  est noté (`match = nearest`) mais n'est pas retenu comme emprise.

### Évaluation

La règle est appliquée à 300 notices tirées au hasard (graine fixe) parmi les
1 283 monuments de type bâtiment dont l'emprise OSM est déjà connue, en partant
du point Mérimée. Le choix est correct si au moins la moitié du bâtiment choisi
est dans l'emprise connue.

| Cas | Notices | Bon bâtiment |
|---|---|---|
| le point est dans un bâtiment | 274 | 262, soit 96 % |
| le point est dehors, bâtiment le plus proche | 19 | 13, soit 68 % |
| aucun bâtiment à portée | 7 | |
| ensemble | 300 | 275, soit 92 % (± 3 points à 95 %) |

D'où la décision de ne retenir que le premier cas. Limite : les notices
évaluées sont celles qu'OSM relie déjà à leur notice ; rien ne garantit que les
autres, souvent des immeubles anonymes, se comportent de même. Le détail par
notice est dans `nearby_buildings_evaluation.csv`.

### Résultat (réponses du 7 octobre 2026)

- 356 notices visées : le point de 338 d'entre elles tombe dans un bâtiment,
  17 sont à côté d'un bâtiment et 1 n'en a aucun à portée.
- 24 bâtiments sont retenus pour plusieurs notices (53 notices), le plus
  souvent plusieurs boutiques protégées d'un même immeuble.
- Le serveur Overpass a renvoyé 32 erreurs pour 22 lots : il a fallu quatre
  exécutions, chacune reprenant la précédente.

### Colonnes de `nearby_buildings.parquet`

GeoParquet en WGS84, une ligne par notice visée ayant un bâtiment à portée :
`merimee_id`, `entity_id` (`way/123`), `match` (`contains` ou `nearest`),
`distance_m`, `building` (l'étiquette OSM) et `geometry`.

## Géométries des monuments

L'étape `geometry` donne à chaque notice un point de référence et une emprise.
Elle ne fait aucun appel réseau.

### Emprise

Par ordre de préférence :

| `footprint_source` | Origine | Notices |
|---|---|---|
| `osm_footprint` | fusion des emprises OSM confirmées par `resolve_entities`, y compris l'objet choisi par un relecteur | 1 374 |
| `osm_line` | lignes OSM confirmées (passages couverts, enceinte, canal), élargies de 3 m de chaque côté ; les relations de type rue ou pôle de transport sont exclues | 41 |
| `osm_nearby` | bâtiment OSM contenant le point de référence, trouvé par `nearby_buildings` | 338 |
| `buffer` | cercle de 10 m de rayon autour du point de référence | 140 |

Parmi les 1 878 monuments protégés, 1 749 (93 %) ont ainsi une emprise réelle
et 129 un cercle : surtout des entourages de métro, des fontaines et des
vestiges d'enceinte.

Les emprises issues d'OSM sont simplifiées avec une tolérance de 1 m, calculée
en Lambert-93. La précision d'un GPS de téléphone est de 5 m au mieux.

### Point de référence

| `point_source` | Règle | Notices |
|---|---|---|
| `osm_footprint` | point à l'intérieur de l'emprise principale | 1 374 |
| `osm_line` | point de la ligne le plus proche du point Mérimée | 41 |
| `osm_node` | nœud OSM portant `ref:mhs`, le plus proche du point Mérimée | 119 |
| `merimee` | point de la notice | 353 |
| `wikidata` | point de l'élément Wikidata principal | 6 |
| `manual` | coordonnées saisies par un relecteur | 0 |

Sans géométrie OSM pour arbitrer, deux points Mérimée et Wikidata distants de
plus de 100 m signalent une erreur dans l'une des sources : la notice est
marquée `point_doubtful`.

### Revue manuelle

`data/interim/geometries_to_review.csv` liste les monuments dont le point est
douteux, avec un lien vers la carte pour chacun des deux points. Les notices
sans protection en sont exclues.

Les choix sont consignés dans `review/geometry_overrides.csv`, versionné.
Colonnes : `merimee_id`, `use`, `lat`, `lon`, `note`.

| `use` | Effet |
|---|---|
| `merimee` | le point Mérimée est retenu |
| `wikidata` | le point de l'élément Wikidata principal est retenu |
| `manual` | les coordonnées `lat` et `lon` de la ligne sont retenues |

Un choix remplace le point de référence et lève le doute. Si l'emprise est un
cercle, il est tracé autour du point choisi.

### Colonnes de `geometries.parquet`

GeoParquet en WGS84 (EPSG:4326), une ligne par notice : `merimee_id`,
`ref_lat`, `ref_lon`, `point_source`, `footprint_source`, `footprint_objects`
(identifiants OSM utilisés, séparés par `;`), `footprint_area_m2`,
`point_gap_m` (écart entre les points Mérimée et Wikidata), `point_doubtful`,
`point_reviewed` et `geometry` (l'emprise).

### Constats (7 octobre 2026)

- 32 emprises sont en plusieurs morceaux. Le schéma du SPEC §5.3 prévoit un
  `polygon` : la table `monuments` utilise un `multipolygon`.
- La simplification ramène les emprises OSM liées de 51 222 à 21 101 sommets
  pour 1 % d'écart de surface ; l'ensemble des emprises pèse 35 566 sommets.
  Une emprise trouvée par `nearby_buildings` garde son tracé complet quand la
  simplification ferait sortir le point de référence.
- 17 notices avaient des points en désaccord. 12 ont été tranchées en
  géocodant l'adresse avec la Base Adresse Nationale : le point Mérimée était
  le bon 9 fois, le point Wikidata 3 fois. 4 ne sont pas des monuments. Il en
  reste une sans adresse pour trancher, le parc Montsouris (`PA00086633`).
- L'usine élévatrice des eaux (`PA00086588`) a été déplacée au parc de la
  Villette : son point Mérimée indique encore l'ancienne adresse.

## Visibilité depuis l'espace public

Un monument dont seul l'intérieur ou une façade sur cour est protégé ne peut pas
être photographié depuis la rue. L'étape `visibility` classe chaque monument
protégé en `visible`, `non_visible` ou `inconnu` à partir du texte qui décrit
la protection (`protection_desc`). Elle ne fait aucun appel réseau.

### Lecture du texte

Le texte est découpé en éléments protégés, aux points-virgules, aux points et
aux tirets qui séparent deux arrêtés. Les références cadastrales entre
parenthèses et la mention de l'arrêté sont retirées. Dans chaque élément,
l'étape repère :

- les **parties extérieures** : façade, toiture, élévation, couverture,
  devanture, enseigne, portail, entourage, balcon, clôture, porche, marquise,
  porte cochère, monumentale ou d'entrée, « porte sur… » ;
- les **parties intérieures** : escalier, rampe, cage, salon, salle, plafond,
  cheminée, boiserie, lambris, vestibule, cave, sous-sol, chambre, appartement,
  pièce, cabinet, décor, hall, foyer, bibliothèque, crypte, peinture, vitraux,
  mobilier, orgue, fresque…

Chaque partie extérieure reçoit le côté indiqué après elle :

| Indice (`evidence`) | Formulation | Exemple |
|---|---|---|
| `street` | sur rue, place, quai, boulevard, avenue, passage ; côté rue ; extérieure, principale, antérieure | « Façade sur rue » |
| `courtyard` | sur cour, jardin ou parc ; côté cour ; postérieure, au fond, entourant la cour | « Façades sur cour et sur jardin » |
| `open` | aucun côté indiqué | « Les façades » |
| `roof` | toiture sans côté indiqué : elle couvre aussi les ailes sur cour, elle ne dit rien | « Toitures » |
| `inside` | partie intérieure | « Escalier avec sa rampe » |
| `whole` | l'élément ne cite aucune partie, il nomme le monument | « Eglise », « La fontaine » |
| `unplaced` | vestige, reste, mascaron, bas-relief ou fragment dont le texte ne dit pas où il est | « Vestiges de l'enceinte » |

Précisions :

- Une façade « sur rue et sur cour » compte pour la rue : 115 monuments ne
  sont visibles que par cette règle.
- Deux parties reliées par « et » partagent le même côté (« façades et toitures
  sur cour »), et une « toiture correspondante » prend celui de la partie qui
  précède.
- Devantures, enseignes, portails, entourages de métro et portes cochères
  donnent sur la rue par nature, sauf mention contraire.
- Un nom suivi de deux-points n'est qu'un titre (« Les parties suivantes de
  l'hôtel … : les trois salons »). Un monument suivi d'ajouts compte en entier
  (« La cathédrale, y compris la crypte »).
- Un monument entier situé dans une cour (« Fontaine sise dans la cour ») ou le
  sol d'une cour ou d'un jardin vaut `courtyard`.

### Classes

La première condition remplie l'emporte. Les effectifs sont ceux des règles,
avant correction manuelle.

| Condition | `visibility` | `reason` | Notices |
|---|---|---|---|
| dénomination « carrière » | `non_visible` | `underground` | 2 |
| dénomination cimetière, jardin, parc, place ou square : un espace ouvert au public | `visible` | `public_grounds` | 21 |
| au moins une partie extérieure côté rue | `visible` | `outside_part_on_street` | 990 |
| au moins une partie extérieure sans côté indiqué | `visible` | `outside_part` | 326 |
| le monument est nommé en entier | `visible` | `whole_monument` | 356 |
| seulement des parties intérieures | `non_visible` | `inside_only` | 108 |
| seulement des éléments sur cour ou sur jardin | `non_visible` | `courtyard_only` | 28 |
| des parties intérieures et des éléments sur cour | `non_visible` | `inside_and_courtyard` | 21 |
| seulement un vestige non situé | `inconnu` | `unplaced_item` | 26 |
| seulement des toitures, ou pas de texte | `inconnu` | `roofs_only`, `no_text` | 0 |

Soit 1 693 `visible`, 159 `non_visible` et 26 `inconnu` pour les 1 878
monuments protégés. Les 15 notices sans protection ne sont pas classées.

### Évaluation

Deux échantillons de monuments, tirés au hasard avec une graine fixe, ont été
étiquetés à la main à partir du texte, du nom et de la dénomination, sans voir
la classe calculée. Ils sont dans `review/visibility_labels.csv`, versionné :
`merimee_id`, `sample`, `label`, `note`.

| `sample` | Notices | Rôle | Accord avec les règles |
|---|---|---|---|
| `dev` | 150 | a servi à ajuster les règles | 143, soit 95 %, à la première mesure ; 149 après ajustement |
| `test` | 100 | étiqueté une fois les règles figées ; ne doit jamais servir à les modifier | 98, soit 98 % (entre 93 % et 99 % à 95 %, intervalle de Wilson) |

La première mesure sur `dev` a conduit à trois ajustements : une toiture sans
côté ne compte plus, un vestige non situé donne `inconnu`, et des ailes
« entourant la cour » comptent pour la cour. Le chiffre de 149 est donc
optimiste ; seul celui de `test` mesure les règles.

Détail de l'échantillon `test` :

| Étiquette | Classé `visible` | Classé `non_visible` | Classé `inconnu` |
|---|---|---|---|
| `visible` (86) | 85 | 1 | 0 |
| `non_visible` (11) | 1 | 10 | 0 |
| `inconnu` (3) | 0 | 0 | 3 |

Les deux désaccords : l'hôpital Cochin (`PA00086616`), dont la dénomination
« carrière » masque une porte sur le boulevard, et des « pavillons intérieurs »
(`PA00088655`) lus comme de simples façades.

L'accord est mesuré sur la sortie des règles, avant toute correction manuelle.
Le détail par notice est dans `visibility_evaluation.csv`.

Limites :

- Les étiquettes jugent le texte, pas le lieu. Un hôtel protégé en entier est
  étiqueté et classé `visible` même s'il se trouve derrière un porche fermé.
  L'accord dit que les règles lisent le texte comme un lecteur attentif, pas
  que le monument se voit réellement depuis la rue.
- Les étiquettes ont été posées par Claude, qui a aussi écrit les règles.
  L'accord est sans doute un peu optimiste tant qu'une seconde personne ne les
  a pas relues.
- L'échantillon `test` ne contient que 11 `non_visible` et 3 `inconnu` : les
  taux par classe sont imprécis.

### Relecture de la classe non visible

Classer à tort un monument `non_visible` le retire du jeu. Les 159 notices que
les règles classent ainsi ont donc toutes été relues : 9 étaient visibles, soit
6 %. Presque toujours, un mot de la liste des parties intérieures désignait
autre chose : la bibliothèque Sainte-Geneviève (l'édifice), les ateliers de
décors de l'Opéra (leur nom), la cheminée d'une usine, des réclames pour une
peinture. L'Opéra Garnier était lu comme un décor intérieur à cause d'une
parenthèse jamais refermée dans la notice.

La classe `visible` est trop grande pour être relue en entier. Deux recherches
ciblées (les textes qui citent à la fois une rue et une cour ; les éléments
rares comptés comme un monument entier) y ont trouvé 3 notices en réalité
masquées et 2 indécidables. D'après l'échantillon `test`, 1 des 86 notices
classées `visible` l'était à tort.

Enfin, 2 des 26 `inconnu` se tranchaient à la lecture.

### Revue manuelle

`data/interim/visibility_to_review.csv` liste les monuments classés `inconnu`,
avec leur texte et le lien vers la notice. Il en reste 27, dont 20 tronçons de
l'enceinte de Philippe-Auguste : le texte ne dit pas s'ils sont dans une cour,
une cave ou sur la rue.

Les corrections sont consignées dans `review/visibility_overrides.csv`,
versionné. Colonnes : `merimee_id`, `visibility`, `note`. La classe indiquée
remplace celle des règles, `reason` vaut alors `reviewed`. Une correction qui
ne correspond à aucun monument protégé est signalée dans le journal.

Le fichier compte 18 corrections : 9 viennent de la relecture de la classe non
visible, 5 des recherches ciblées, 2 des désaccords relevés à l'étiquetage et 2
des `inconnu` tranchés. Elles font passer 11 monuments en `visible`, 4 en
`non_visible` et 3 en `inconnu`.

### Colonnes de `visibility.parquet`

Une ligne par monument protégé : `merimee_id`, `visibility`, `reason`,
`evidence` (les indices lus, dans l'ordre du texte : `facade: street;
escalier: inside`) et `reviewed`. `evidence` reste celui des règles même quand
la classe a été corrigée.

### Constats (8 octobre 2026)

- Après correction : 1 697 monuments `visible` (90 %), 154 `non_visible` (8 %)
  et 27 `inconnu` (1 %).
- Les 154 `non_visible` sont surtout des intérieurs : escaliers, décors de
  cafés et de boulangeries, salles de spectacle, caves.
- La protection d'un hôtel particulier « en totalité » ne dit rien de sa
  visibilité. C'est la principale source d'erreur restante, et le texte ne
  permet pas de la lever.

## Photos de référence (Wikimedia Commons)

L'étape `ingest_commons` liste les photos que Wikimedia Commons possède pour
chaque monument, lit leur auteur, leur licence, leur date et leurs dimensions,
puis retient celles qui peuvent servir de photo de référence : une photographie
récente de l'extérieur, assez grande, sous licence libre. Elle ne télécharge
aucune image : elle ne lit que des descriptions.

### Sources

- **Service** : API de Commons, <https://commons.wikimedia.org/w/api.php>.
  Chaque fichier a sa propre licence, conservée avec le nom de l'auteur.
- **Point de départ** : la catégorie Commons (P373) et l'image principale (P18)
  de l'élément Wikidata principal de chaque monument protégé.
- **Fichiers lus**, dans cet ordre de préférence quand un fichier se trouve à
  plusieurs endroits :

| `source` | Origine |
|---|---|
| `main_image` | l'image principale de l'élément Wikidata |
| `category` | les fichiers rangés directement dans la catégorie du monument |
| `exterior_subcategory` | les fichiers des sous-catégories de vues extérieures (« Exterior of… », « Facade of… », « Entrances to… ») |
| `subcategory` | pour un monument qui garderait moins de 5 photos sans elles : les sous-catégories d'images distinguées (« Quality images of… ») et celles des adresses qui composent le monument (« 12 place Dauphine, Paris ») |

- **Sous-catégories** : un seul niveau. Celles dont le nom annonce un autre
  sujet (« Interior of… », « Historical images of… », « Events at… ») ne sont
  jamais lues, ni celles qui sont la catégorie d'un autre monument. Les autres
  ne sont pas lues non plus : on y trouve des répliques, des événements, les
  occupants de l'immeuble.
- **Limite** : les 500 premiers fichiers d'une catégorie.

### Requêtes

- Le client s'identifie par un en-tête `User-Agent` avec contact et envoie
  `maxlag=5` : un serveur occupé répond alors par une erreur « maxlag » et la
  requête est renvoyée après l'attente indiquée.
- Les requêtes se suivent une à une. Commons décrit 50 fichiers par réponse :
  les suivants arrivent dans les réponses d'après.
- Chaque réponse est ajoutée aussitôt à un fichier de `data/raw/commons/`, une
  ligne JSON par catégorie ou par fichier. Une exécution interrompue reprend
  donc où elle s'était arrêtée, et les suivantes ne redemandent que ce qui
  manque.

Options : `--offline` rejoue l'étape avec les seules réponses enregistrées ;
`--refresh` les oublie et redemande tout.

### Tri des fichiers

Un fichier est écarté pour la première raison rencontrée dans cet ordre :

| `reject_reason` | Règle |
|---|---|
| `format` | ce n'est pas un JPEG (PNG de plans et de logos, TIFF d'archives, vidéos, PDF) |
| `licence` | la licence n'est ni le domaine public, ni CC0, ni CC BY, ni CC BY-SA, ni une licence équivalente |
| `old` | l'image date d'avant 1950 : autre état du monument, gravure, photographie ancienne |
| `inside` | un mot annonce un intérieur : « intérieur », « escalier », « nef », « salle »… |
| `detail` | un mot annonce un détail : « détail », « plaque », « fenêtre », « balcon »… |
| `sculpture` | un mot annonce un élément sculpté : « statue », « mascaron », « bas-relief »… |
| `document` | un mot annonce un document : « plan », « gravure », « Musée Carnavalet », « Gallica »… |
| `other` | un mot annonce un autre sujet : « events », « travaux », « aerial »… |
| `small` | le petit côté de l'image fait moins de 640 px |

Sur 40 295 fichiers trouvés (39 530 distincts, 640 servant à plusieurs
monuments), 27 169 sont gardés. Les autres sont écartés pour : `old` 5 023,
`inside` 2 602, `document` 1 523, `detail` 1 509, `other` 1 124, `small` 584,
`format` 426, `sculpture` 305, `licence` 30.

Les mots sont cherchés dans le nom du fichier et, pour la plupart, dans ses
catégories, sans tenir compte des accents ni de la casse. Trois précautions :

- **Le nom dit le sujet, la catégorie non.** Les mots de détail et de sculpture
  ne comptent que dans le nom du fichier. En catégorie, ils décrivent souvent un
  élément que la photo contient seulement : « Windows in Paris » se trouve sur
  des photos de façades entières.
- **Un mot du nom du monument ne compte pas contre lui** : « salle » ne dit rien
  des photos de la salle Pleyel.
- **Le sujet même du monument non plus** : les mots d'intérieur ne s'appliquent
  pas à un passage couvert, ni les mots de sculpture à une fontaine, un
  monument ou un tombeau.

Les **stations de métro** suivent une règle à part. Leur catégorie Commons
couvre toute la station (quais, couloirs, guichets) alors que seuls les
entourages et édicules d'entrée sont protégés : une photo n'est gardée que si
son nom ou ses catégories citent une entrée (« accès », « entrance »,
« édicule », « Guimard »…).

### Sélection

Les photos gardées d'un monument sont classées (`rank`), et les 15 premières
sont sélectionnées (`selected`) :

1. l'image principale de l'élément Wikidata ;
2. les photos distinguées par Commons (image de qualité, image remarquable) ;
3. les autres, en alternant les séances — un auteur, une année — de la plus
   récente à la plus ancienne : deux photos d'une même séance montrent plus
   souvent le même angle sous la même lumière.

Le classement sélectionne 11 983 photos : 8 860 viennent de la catégorie,
1 686 sont des images principales, 1 180 viennent d'une sous-catégorie de vues
extérieures et 257 d'une sous-catégorie de secours.

### Évaluation

Le tri ne lit que des mots : pour savoir ce qu'il vaut, il faut regarder les
images. 445 vignettes ont été regardées par planches de 20, sans connaître la
décision du tri, et étiquetées `ok` (vue de l'extérieur du monument, à l'échelle
du bâtiment), `inside`, `detail`, `document` ou `other`. Quand l'image seule ne
suffisait pas (cette fontaine est-elle le monument ?), le nom du fichier et la
notice ont été consultés. Les étiquettes sont dans `review/commons_labels.csv`,
versionné : `merimee_id`, `title`, `sample`, `label`, `note`. Toutes les
photos viennent de monuments classés `visible`.

| `sample` | Photos | Rôle | Résultat |
|---|---|---|---|
| `dev` | 285 | deux lots qui ont servi à ajuster les règles : 100 photos sélectionnées et 60 écartées, puis 25 photos sélectionnées par source | 182 bonnes vues sur les 220 photos encore gardées, soit 83 % : chiffre optimiste |
| `test` | 160 | tiré une fois les règles figées, parmi les photos jamais regardées : 100 sélectionnées et 60 écartées pour leur sujet | **75 photos sélectionnées sur 100 sont de bonnes vues** (entre 66 % et 83 % à 95 %) ; 55 des 60 mises à l'écart sont justifiées (entre 82 % et 96 %) |

Les deux lots `dev` ont conduit à trois ajustements : les mots de détail et de
sculpture ne comptent plus que dans le nom du fichier (ils écartaient à tort 11
bonnes photos sur 26), la règle des stations de métro, et la restriction des
sous-catégories de secours.

La mesure a été faite avec un seuil de taille à 1 000 px, abaissé ensuite à
640 px (voir les constats). La décision ne change pour aucune des 160 photos
de `test` ; les photos de 640 à 999 px n'en faisaient pas partie. Dans `dev`,
5 des 6 photos de cette taille sont de bonnes vues.

Détail de l'échantillon `test` :

- Les 25 photos sélectionnées à tort montrent un détail (11), un intérieur (6),
  un autre sujet (6) ou un document (2). Aucun mot de leur nom ni de leurs
  catégories ne le dit.
- Par source : les 15 images principales sont toutes bonnes, contre 53 des 75
  photos de catégorie et 6 des 8 photos de sous-catégories extérieures. Sur
  l'ensemble des photos étiquetées, 56 images principales sur 57 sont bonnes.
- Par rang : 16 bonnes vues sur 17 au rang 1, 29 sur 35 aux rangs 2 à 5, 28 sur
  46 aux rangs 6 à 15. Les premières photos sont les plus sûres.

Limites :

- Un quart des photos sélectionnées ne conviennent pas, et les mots ne
  permettent pas de faire mieux. Le tri fin demande de regarder l'image : il
  pourra se faire à l'étape des embeddings, quand les images seront
  téléchargées et qu'un modèle de vision sera disponible.
- `ok` dit que la photo montre l'extérieur d'un bâtiment, pas que c'est le bon :
  une catégorie peut contenir la photo d'un immeuble voisin.
- Les étiquettes ont été posées par Claude, qui a aussi écrit les règles, sur
  des vignettes de 500 px. Les cas limites sont notés (une porte cochère cadrée
  serré compte pour une bonne vue).
- Les intervalles sont larges : 100 photos sélectionnées, 60 écartées.

Le détail par photo est dans `data/interim/commons_evaluation.csv`. Les 23
planches regardées et leur index (`index.csv`, avec le lien de chaque photo)
sont conservés hors git dans `data/raw/commons/evaluation/`.

### Colonnes de `commons_files.parquet`

Une ligne par monument et par fichier trouvé pour lui, gardé ou non :

| Colonne | Type | Contenu |
|---|---|---|
| `merimee_id` | texte | notice du monument |
| `title` | texte | titre du fichier sur Commons (`File:…`) |
| `source` | texte | où le fichier a été trouvé, voir plus haut |
| `category` | texte | la catégorie ou sous-catégorie qui le contient, vide pour une image principale |
| `page_url` | texte | page du fichier, à citer comme source |
| `thumb_url` | texte | vignette de 960 px de large |
| `width`, `height` | entiers | dimensions de l'original |
| `mime` | texte | type du fichier |
| `author` | texte | auteur à créditer : le nom déclaré, en texte brut, lu dans la notice quand le champ en contient une |
| `uploader` | texte | compte qui a versé le fichier |
| `licence`, `licence_url` | texte | nom court de la licence et lien vers son texte |
| `year` | entier | année de la prise de vue, lue dans la date déclarée |
| `camera_lat`, `camera_lon` | réels | position de l'appareil, quand elle est déclarée |
| `reject_reason` | texte | raison de l'écarter, vide si le fichier est gardé |
| `rank` | entier | rang parmi les fichiers gardés du monument |
| `selected` | booléen | vrai pour les 15 premiers rangs |

`commons_categories.parquet` donne, pour chaque catégorie de monument, le
nombre de fichiers (`files`) et de sous-catégories (`subcats`) qu'elle
contient. Il servira au score de rareté.

### Constats (réponses du 8 octobre 2026)

- **Couverture** : 1 796 monuments sur 1 878 ont au moins une photo
  sélectionnée. Parmi les 1 697 monuments visibles depuis la rue :

| Photos sélectionnées | Monuments visibles |
|---|---|
| 0 | 55 (3 %) |
| 1 à 4 | 804 (47 %) |
| 5 à 14 | 428 (25 %) |
| 15 | 410 (24 %) |

- **L'objectif du SPEC n'est pas atteignable** : moins d'un monument visible
  sur deux (49 %) a 5 photos, la médiane est de 4. Commons a beaucoup de photos
  des monuments connus et une ou deux de la plupart des immeubles protégés.
- **Métro** : 44 des 68 stations protégées ont des photos de leurs entrées, 35
  en ont au moins 5 ; 24 n'en ont aucune.
- **Licences de la sélection** : CC BY-SA 78 %, CC BY 17 %, domaine public ou
  CC0 5 %. Presque toutes demandent de citer l'auteur : la sélection en compte
  1 459.
- **Nom à créditer** : quelques photographes remplissent le champ « auteur »
  avec toute une notice (« Thank you to indicate this credit line next to the
  image in case of reuse: Credit: Polymagou - CC BY-SA… », jusqu'à 1 041
  caractères). Trois familles de notices sont reconnues — la ligne de crédit
  demandée, « This photograph was taken by… », « No machine-readable author
  provided. … assumed » — ainsi que les fichiers venus d'une Wikipédia (« The
  original uploader was… ») ; le nom en est extrait. 345 fichiers sont
  concernés, dont 141 de la sélection, pour 39 notices différentes, toutes
  relues. Le classement des photos continue de se faire sur le champ tel qu'il
  est déclaré : la sélection ne change pas. Les autres auteurs sont gardés
  tels quels, même longs (« Jules, Louis et Henri Séeberger © Reproduction
  Philippe Berthé / CMN »).
- **Taille** : le seuil était d'abord de 1 000 px. Il écartait 1 492 fichiers,
  souvent de bonnes photos (6 sur 7 dans le premier lot regardé). À 640 px,
  assez pour un modèle qui lit des images de 224 px, 908 fichiers de plus sont
  gardés et 10 monuments visibles gagnent leur première photo (décision du
  8 octobre 2026).
- **Position de l'appareil** : déclarée pour la moitié des photos
  sélectionnées, mais sans usage pour le tri. Comparée à l'emprise du monument,
  elle ne distingue pas les bonnes vues : beaucoup de contributeurs indiquent
  la position du bâtiment, pas la leur.
- **Piège de l'API** : pour un fichier téléversé plusieurs fois, Commons
  propose de « continuer » vers ses anciennes versions (`iistart`). Suivre
  cette piste remplace la description courante par celle d'une version
  archivée, ou tourne en rond. L'étape ne suit que la continuation des
  fichiers (`iicontinue`).

## Sélection des monuments montrés

La base recense tous les immeubles protégés : 1 878 à Paris, dont une
majorité d'immeubles d'habitation sans nom (« Immeuble, 45 rue Saint-Merri »)
devant lesquels un promeneur ne s'arrête pas. L'étape `selection` choisit ceux
que l'app montre, en se demandant : en passant devant, aurait-on envie d'en
savoir plus ? (décisions du 11 octobre 2026)

### 1. Les candidats : un article dans Wikipédia

Un monument est candidat quand quelqu'un a jugé qu'il méritait un article dans
Wikipédia en français :

1. l'objet Wikidata de sa notice a un article ;
2. ou il a un nom propre et l'article porte sur ce qui l'occupe ou le
   contient. L'article d'un lycée ou d'un musée est rattaché à
   l'établissement, pas au bâtiment que la notice protège : Wikidata dit que le
   bâtiment est « occupé par » lui (P466) ou en « fait partie » (P361), ou que
   l'établissement y a son « siège » (P159), son « lieu » (P276), ou le
   « comprend » (P527). Quand plusieurs articles se présentent, celui dont le
   sujet a le plus de liens entre sites est retenu. C'est ainsi que sont
   retrouvés le lycée Louis-le-Grand, le musée d'Orsay, l'Institut Pasteur,
   l'hôtel Carnavalet ou l'église Saint-Germain-des-Prés.

Le nom propre est exigé dans le second cas parce qu'un immeuble anonyme ne
devient pas intéressant du fait de son locataire (« Zara », « Marriott »).

Les **stations de métro** sont écartées quel que soit leur article
(`EXCLUDED_KINDS`) : les 68 notices protègent leurs entrées, toutes semblables.

Il reste 833 candidats : 766 par leur article, 67 par celui d'un voisin.

### 2. Le classement : lectures et langues

Les candidats sont classés par deux mesures de la curiosité qu'ils suscitent :

- **les lectures de l'article sur un an**, d'octobre 2025 à septembre 2026,
  par des personnes et non des robots (API des statistiques de Wikimedia) :
  de 497 390 pour la tour Eiffel à moins de 100, médiane 3 418 ;
- **le nombre de sites qui ont un article sur le sujet** (`wikibase:sitelinks`),
  proche du nombre de langues : 191 pour la tour Eiffel, 1 ou 2 pour un
  article qui n'existe qu'en français.

Le score est la moyenne des deux places du monument parmi les candidats,
chacune de 0 (le dernier) à 1 (le premier). Les ex æquo sont départagés par
l'identifiant, pour que l'ordre ne change pas d'une exécution à l'autre.

Le nombre de photos sur Commons a été écarté comme mesure : un lieu connu peut
n'avoir aucune photo dans sa catégorie.

### 3. La coupe

L'app montre les candidats jusqu'à la 350e place (`LAST_RANK_SHOWN`), à deux
conditions :

- **on peut se tenir devant** (voir « Niveaux de préparation ») : les vestiges
  que rien ne situe et la carrière souterraine n'ont pas leur place sur une
  carte faite pour se promener ;
- **aucune décision à la main ne les cache.**
  `review/selection_overrides.csv` (`merimee_id`, `name`, `decision`, `note`)
  montre (`show`) ou cache (`hide`) un monument quelle que soit sa place.

La coupe a été choisie sur pièces : à la 200e place, on perdait l'église
Saint-Louis-en-l'Île, l'hôtel de Cluny, la Cigale ; à la 500e, il restait 100
hôtels particuliers, pour beaucoup inconnus. La 350e place correspond à
environ 2 000 lectures par an.

### Résultat

| | Monuments |
|---|---|
| **montrés** | **323** |
| trop peu connus (au-delà de la 350e place) | 479 |
| sans article | 977 |
| d'un genre écarté (stations de métro) | 68 |
| on ne peut pas se tenir devant | 24 |
| cachés à la main | 7 |
| total | 1 878 |

Parmi les 323 : 53 églises, 42 hôtels particuliers, 30 théâtres, 10
immeubles, pour 77 genres différents. Tous sont capturables.

### Limites

- **Un monument hérite de la notoriété de son occupant.** C'est juste pour un
  lycée ou un musée, faux pour un bâtiment parmi d'autres d'une grande
  institution : le presbytère de Notre-Dame se classait 3e grâce à l'article
  de la cathédrale, deux bâtiments 5e et 6e grâce à celui de Sciences Po. Les
  sept cas repérés dans les 350 premiers sont cachés à la main.
- **Des monuments connus restent sans article** quand Wikidata ne fait aucun
  lien : l'ancienne École polytechnique, les hôtels de Rohan et Soubise
  (Archives nationales), le pavillon de la Reine, l'Institut national des
  jeunes aveugles. Ils se rattrapent par une décision `show`.
- **Les lectures suivent l'actualité** : le Bataclan est 19e.
- **Rien n'est supprimé** : `selection.parquet` garde une ligne par monument
  (`shown`, `reason`, `left_out`, `article`, `views`, `languages`, `score`,
  `rank`) ; les autres tables et la base Postgres conservent les 1 878
  monuments. Seul le fichier de l'app est filtré.

`data/interim/selection_ranking.csv` donne le classement des 833 candidats
avec leur nom, pour le relire. Les réponses des services sont conservées dans
`data/raw/wikidata/neighbours.json` et `data/raw/wikipedia/pageviews.json` ;
`--offline` les rejoue.

## Chargement dans Postgres

L'étape `load_postgres` remplit les tables `monuments` et `reference_images`,
créées par les migrations de `supabase/migrations/`. C'est la moitié « base de
données » de l'étape 11 du SPEC ; le bundle SQLite de l'app viendra avec elle.

### Mode d'emploi

```bash
supabase start                 # depuis la racine du dépôt : démarre la base locale
supabase migration up          # applique les migrations qui manquent
cd pipeline
uv run python -m lutece_pipeline.load_postgres
```

Pour charger une autre base, donner son adresse dans la variable
d'environnement `LUTECE_DATABASE_URL`. Elle contient un mot de passe : ne pas
l'écrire dans un fichier versionné. Le journal l'affiche sans le mot de passe.

### Ce que fait un chargement

- **Une transaction** : tout est écrit, ou rien.
- **Rejouable** : l'identifiant d'un monument est calculé à partir de sa
  référence Mérimée, celui d'une photo à partir du monument et du nom du
  fichier. Un second chargement met donc à jour les mêmes lignes, et les
  captures des joueurs pourront pointer vers un monument sans risque.
- **Ce qui est conservé** : les colonnes que les étapes suivantes rempliront
  (rareté, fiches, empreinte d'image) et les photos apportées par les joueurs.
- **Ce qui est retiré** : les photos que le pipeline ne sélectionne plus.
- **Un monument sorti du pipeline** est compté dans le journal mais pas
  supprimé.

### Contenu des tables

| Colonne de `monuments` | Origine |
|---|---|
| `id` | calculé à partir de `merimee_id` |
| `merimee_id`, `name`, `address`, `arrondissement`, `protection`, `protection_desc` | notice Mérimée |
| `category` | première dénomination de la notice |
| `period_start` | siècle de construction : 17 pour le XVIIe siècle |
| `architects` | ceux de la notice, à défaut ceux de Wikidata |
| `wikidata_qid` | élément principal retenu par `resolve_entities` |
| `osm_id` | premier objet OpenStreetMap de l'emprise (`way/123`) |
| `location`, `footprint`, `footprint_source` | `geometries.parquet` ; un cercle de 10 m quand `footprint_source` vaut `buffer` |
| `visibility` | `visibility.parquet` |
| `sources` | les bases d'où vient le monument, avec lien et licence |
| `data_version` | numéro du chargement |
| `rarity_score`, `rarity_tier`, `summary_fr`, `story_fr` | vides : étapes à venir |

`reference_images` contient les photos sélectionnées par `ingest_commons` :
`source_url` (la page du fichier, à créditer), `thumb_url`, `author`,
`licence`, `licence_url`, `rank`. `embedding` reste vide jusqu'à l'étape des
embeddings.

Les deux tables sont en lecture publique et protégées en écriture par la
sécurité au niveau des lignes : seul le pipeline, connecté comme
administrateur, les modifie.

### Résultat (base locale, 8 octobre 2026)

- 1 878 monuments et 11 983 photos chargés en 3 secondes ; un second
  chargement ne change rien.
- Tous les monuments ont un point et une emprise valide ; 1 829 ont une
  adresse, 813 un architecte.
- Autour d'un point du parvis de Notre-Dame, la recherche à 150 m que fera
  l'app renvoie la cathédrale (19 m), l'Hôtel-Dieu (35 m), le presbytère
  (59 m) et un ancien débit de boisson (134 m), en passant par l'index
  spatial.

### Tests

Un test charge deux monuments fictifs dans la base locale, à l'intérieur d'une
transaction qu'il annule : la base n'est pas modifiée. Il est ignoré quand la
base locale ne tourne pas.

## Fichier embarqué dans l'app

L'app fonctionne hors ligne : tout ce qu'elle affiche des monuments vient d'un
fichier SQLite que l'étape `export_bundle` écrit dans ses ressources,
`apps/mobile/assets/data/lutece.db`. C'est la moitié « app » de l'étape 11 du
SPEC. Le fichier pèse 0,9 Mo et il est versionné : l'app se compile sans
relancer le pipeline.

### Contenu

| Table | Lignes | Contenu |
|---|---|---|
| `monuments` | 323 | une ligne par monument que la sélection garde |
| `photos` | 933 | les 3 premières photos sélectionnées de chaque monument, avec auteur et licence |
| `meta` | 3 | version du contenu et effectifs |

Colonnes de `monuments` : `id` (le même identifiant que dans Postgres),
`merimee_id`, `title`, `name`, `address`, `arrondissement`, `lat`, `lon`,
`min_lat`, `max_lat`, `min_lon`, `max_lon` (le cadre de l'emprise),
`footprint` (multipolygone GeoJSON en WGS84, 6 décimales), `footprint_source`,
`category`, `century`, `architects` (tableau JSON), `wikidata_qid`,
`protection`, `visibility`, `readiness`, `capture_reach_m` et `photo_count`.

- **`title`** est ce que l'app affiche : le nom du monument, ou son genre suivi
  de sa première adresse quand il n'a pas de nom propre (« Immeuble, 12 rue
  Volta »). Les monuments qui portent le même titre reçoivent aussi leur
  adresse : trente immeubles s'appellent « Immeuble en bordure du
  Palais-Royal ».
- **`readiness`** reprend les niveaux du rapport de qualité : `ready`,
  `approximate`, `not_ready`.
- **`capture_reach_m`** est la distance, en mètres, jusqu'à laquelle on peut
  capturer le monument quelle que soit la précision du GPS (voir ci-dessous).

### Distance de capture

Le SPEC (§6.1) retient les monuments dont l'emprise est à moins de
`clamp(2 × précision GPS, 50 m, 150 m)`. Avec un bon GPS, cela fait 50 m : trop
peu pour un monument qu'on photographie de loin, et impossible pour l'Arc de
Triomphe, dont le trottoir le plus proche est à plus de 100 m. L'app prend
donc la plus grande de deux distances : celle du SPEC, qu'elle calcule
elle-même, et `capture_reach_m`, qui vaut 0 sauf pour les monuments de
`review/capture_reach.csv` (`merimee_id`, `name`, `reach_m`, `note`).

Ce fichier, tenu à la main, liste 24 monuments qu'on voit de loin, par-dessus
les toits ou au bout d'un espace dégagé : tour Eiffel 800 m, Hôtel des
Invalides 500 m, Notre-Dame, Panthéon et palais de Chaillot 400 m, Arc de
Triomphe, Sacré-Cœur, Opéra Garnier, Madeleine et École militaire 300 m,
palais du Luxembourg 250 m, puis des colonnes, tours, portes, églises et
palais devant une place ou un fleuve (150 à 200 m).

**La taille de l'emprise n'entre plus dans le calcul.** Du 10 au 12 octobre
2026, la distance valait au moins deux fois la longueur de l'emprise, jusqu'à
300 m. L'essai dans la rue l'a invalidée : depuis la rue Soufflot, le lycée
Saint-Louis, long de 128 m, se capturait à 254 m, derrière plusieurs pâtés de
maisons. Un bâtiment long n'est pas plus visible de loin qu'une maison ; 135
monuments sur 323 avaient ainsi une portée de plus de 150 m.

La géométrie seule ne sait pas ce qui s'interpose entre le joueur et le
monument : à 50 m, on capture encore à travers un immeuble. C'est la
comparaison d'images (phase 3) qui dira si le monument est dans le cadre, et
qui permettra d'allonger les distances sans risque. La validation côté serveur
devra appliquer la même règle : la colonne sera à charger dans Postgres à ce
moment-là.

### Version

`bundle.json` donne à l'app la version du fichier avant qu'elle l'ouvre. Cette
version est une empreinte du contenu : elle change dès qu'une valeur change,
sans numéro à incrémenter. L'app nomme sa copie d'après elle
(`monuments-<version>.db`), si bien qu'un nouveau fichier remplace l'ancien à
la mise à jour. La collection du joueur vivra dans une autre base, qu'aucune
mise à jour ne remplace.

Deux exécutions sur les mêmes données donnent le même fichier, octet pour
octet.

## Rapport de qualité

L'étape `quality_report` croise les tables des autres étapes : une ligne par
monument protégé, avec ce que la base sait de lui et ce qui lui manque. Elle
écrit aussi un rapport en français. Elle ne fait aucun appel réseau. Son numéro
est celui du SPEC : les étapes 8 à 11 (fiches, rareté, embeddings, export)
viendront dans les phases suivantes.

### Sorties

- `data/processed/monuments_quality.parquet` : la table par monument.
- `data/processed/quality_problems.csv` : une ligne par monument et par
  problème, avec le lien vers la notice.
- `docs/rapport/qualite-donnees.md` : le rapport, versionné pour être lisible
  hors de la machine qui l'a produit. Il est réécrit à chaque exécution : ne pas
  le modifier à la main.

### Niveaux de préparation

| `readiness` | Condition | Monuments |
|---|---|---|
| `ready` | on peut se tenir devant, et son contour est réel | 1 741 (93 %) |
| `approximate` | on peut se tenir devant, mais il est repéré par un cercle de 10 m | 109 (6 %) |
| `not_ready` | souterrain, ou vestige que rien ne situe | 28 (1 %) |

Jusqu'au 11 octobre 2026, un monument n'était prêt que s'il était `visible`
au sens de l'étape 6, c'est-à-dire si **ce que la notice protège** se voyait de
la rue. Le lycée Louis-le-Grand, dont seules les « façades sur cour » sont
protégées, n'était donc pas capturable, alors qu'on passe devant rue
Saint-Jacques. La question posée est désormais celle du lieu : peut-on se
tenir devant ? Seuls restent à l'écart la carrière souterraine (1) et les
monuments à la visibilité `inconnu` (27), pour l'essentiel des vestiges de
l'enceinte de Philippe-Auguste dont le texte ne dit pas où ils sont. La
visibilité de l'étape 6 est conservée telle quelle : elle dit toujours si
l'élément protégé se voit, ce que l'app signale sur la fiche.

### Colonnes de `monuments_quality.parquet`

| Colonne | Type | Contenu |
|---|---|---|
| `merimee_id`, `name`, `arrondissement`, `protection` | | repris de la notice |
| `category` | texte | première dénomination de la notice |
| `has_own_name` | booléen | faux si le nom ne dit que le genre du bâtiment |
| `has_wikidata`, `has_frwiki` | booléens | fiche Wikidata, article Wikipédia en français |
| `has_century`, `has_history` | booléens | siècle de construction et historique dans la notice |
| `has_architect` | booléen | architecte cité par la notice ou par Wikidata |
| `footprint_source`, `point_doubtful` | | repris de `geometries.parquet` |
| `visibility` | texte | repris de `visibility.parquet` |
| `photos` | entier | nombre de photos sélectionnées par `ingest_commons` |
| `readiness` | texte | voir ci-dessus |

Un nom est générique quand il se réduit à une dénomination (« Immeuble »,
« Hôtel (ancien) ») ou à un seul mot (« Boulangerie »), sauf nom propre à trait
d'union (« Pont-Neuf »). C'est le cas de 775 monuments, que l'app devra nommer
par leur adresse.

### Problèmes relevés

| `problem` | Sens | Monuments |
|---|---|---|
| `no_wikidata_item` | pas de fiche Wikidata, donc ni article ni photos | 10 |
| `no_footprint` | repéré par un cercle, faute de contour | 129 |
| `doubtful_point` | points Mérimée et Wikidata en désaccord, non tranché | 1 |
| `visibility_unknown` | visibilité à trancher | 27 |
| `no_photo` | visible depuis la rue mais sans photo | 55 |

### Constats (8 octobre 2026)

- **La géographie est prête, les fiches non.** 1 697 monuments peuvent être
  proposés à la capture, dont 1 642 avec au moins une photo. Mais 741 seulement
  ont un article Wikipédia en français, et 39 % des notices ont un historique :
  la rédaction des fiches sera le point faible.
- **Les monuments sont très inégalement répartis** : 248 dans le 1er et 255
  dans le 4e, contre 19 dans le 20e. Les arrondissements périphériques en ont
  peu, mais mieux documentés (95 % d'articles Wikipédia dans le 20e, 31 % dans
  le 1er).
- **Deux types sont mal lotis** : 40 des 68 stations de métro n'ont qu'un
  cercle, leur entrée étant un simple point dans OpenStreetMap ; 20 des 21
  tronçons d'enceinte attendent qu'on tranche leur visibilité.
- **Les immeubles anonymes dominent** : 710 monuments sont des « immeubles »,
  prêts à 92 % mais avec 2 photos en médiane et 10 % d'articles Wikipédia.

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
- §5.2, étape 3 : `ref:mhs` seul n'atteint que 799 notices (42 %). L'étiquette
  `wikidata` est ajoutée comme seconde clé, ce qui porte la couverture à 1 705
  notices (90 %).
- §5.2, étape 3 : les « emprises des bâtiments autour » ne sont pas chargées
  en bloc. L'étape `nearby_buildings` les demande seulement pour les monuments
  restés sans emprise après le rapprochement (décision du 7 octobre 2026).
- §5.2, étape 4 : l'appariement par distance et similarité de nom sert à
  contrôler les liens exacts plutôt qu'à en créer. La recherche d'un bâtiment
  par proximité, pour les notices sans objet OSM, relève de l'étape
  `nearby_buildings`.
- §2 et §5.2, étape 6 : le texte de protection permet de reconnaître une
  protection d'intérieur ou de façade sur cour, pas une « cour privée fermée ».
  Un hôtel protégé en entier est classé `visible` même s'il se trouve derrière
  un porche. L'étape juge le texte ; la visibilité réelle reste à confirmer par
  les photos ou sur place.
- §5.2, étape 7 : l'objectif de « 5 à 15 photos par monument » n'est atteint
  que pour 49 % des monuments visibles ; 55 n'en ont aucune.
- §5.2, étape 7 : le filtre « extérieur, pas de gros plan de détail » ne peut
  pas être tenu avec les seules descriptions des fichiers. Mesuré sur 100
  photos, il laisse passer un quart de photos qui ne conviennent pas. Un tri
  sur l'image elle-même est à prévoir avec les embeddings.
- §5.3 : la table `monuments` s'écarte du schéma sur trois points, décidés
  le 8 octobre 2026 : `footprint` est un `multipolygon` (32 monuments en
  plusieurs morceaux) ; une colonne `address` permet de nommer les 775
  monuments sans nom propre ; une colonne `footprint_source` distingue un
  contour réel d'un cercle. `reference_images` reçoit `thumb_url`,
  `licence_url` et `rank`.
- §5.3 : seules `monuments` et `reference_images` sont créées. Les tables des
  joueurs (profils, captures, séries) viendront avec l'app.
- §5.2, étape 7 : les « fichiers portant le modèle Mérimée » ne sont pas
  cherchés. Sur 60 monuments, cette recherche n'apportait 5 photos qu'à 2 des
  29 monuments qui en manquaient.
- §6.1 : la distance de capture `clamp(2 × précision GPS, 50 m, 150 m)` est
  trop courte pour les monuments qu'on voit de loin. Elle est complétée par une
  distance fixée à la main pour 24 d'entre eux (décisions des 10 et 12 octobre
  2026, voir « Distance de capture »).
- §4 et §6.1 : `expo-location` ne donne pas la précision du cap en degrés sur
  iOS, mais un niveau de 0 à 3 (3 : moins de 20°, 2 : moins de 35°, 1 : moins
  de 50°). Le cône « cap ± (30° + précision du cap) » utilise la borne du
  niveau, et la visée est refusée au niveau 0 (décision du 10 octobre 2026).
- §5.3 : en attendant les comptes, les captures sont enregistrées sur le
  téléphone, dans une table `captures` qui reprend celle du SPEC sans
  `user_id`. `heading_accuracy_deg` y devient `heading_level` (le niveau de la
  boussole), et deux colonnes s'ajoutent : `chosen_by_player`, vrai quand le
  joueur a désigné le monument parmi plusieurs candidats, et `photo_file`
  (décision du 11 octobre 2026).
- §5.2 : une étape `selection`, absente du SPEC, choisit les monuments que
  l'app montre : les 350 plus connus de ceux qui ont un article dans Wikipédia
  en français, hors stations de métro, soit 323 monuments sur 1 878 (décision
  du 11 octobre 2026, voir « Sélection des monuments montrés »). Les lectures
  des articles, que le §5.5 destinait au score de rareté, servent ici à
  choisir ce qu'on montre.
- §5.2, étape 6 : la visibilité ne décide plus de ce qui se capture. Un
  monument est capturable dès qu'on peut se tenir devant, même si seul son
  intérieur ou sa cour est protégé (décision du 11 octobre 2026, voir
  « Niveaux de préparation »).
