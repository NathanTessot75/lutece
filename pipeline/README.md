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
notices.

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
  `polygon` : il faudra un `multipolygon` au chargement.
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
