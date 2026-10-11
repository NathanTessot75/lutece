# Qualité de la base des monuments

Rapport produit par `uv run python -m lutece_pipeline.quality_report`,
à partir des tables du pipeline. Ne pas le modifier à la main.

## En bref

- La base compte **1 878 monuments** protégés à Paris.
- **1 741 (93 %) sont prêts pour l'app** : on peut se tenir devant,
  et le contour de leur bâtiment est connu.
- 109 (6 %) sont prêts avec réserve : repérés par un simple
  cercle de 10 m.
- 28 (1 %) ne sont pas prêts : souterrains, ou
  vestiges que rien ne situe.
- Parmi les 1 850 monuments prêts, avec ou sans réserve,
  1 775 ont au moins une photo de référence et
  797 ont aussi un article Wikipédia.

## Ce que la base sait de chaque monument

| Information | Monuments |
|---|---|
| Fiche Wikidata | 1 868 (99 %) |
| Contour réel du bâtiment | 1 749 (93 %) |
| Visible depuis la rue | 1 697 (90 %) |
| Au moins une photo de référence | 1 796 (96 %) |
| Au moins 5 photos de référence | 905 (48 %) |
| Siècle de construction | 1 625 (87 %) |
| Article Wikipédia en français | 830 (44 %) |
| Architecte connu | 813 (43 %) |
| Historique dans la notice | 737 (39 %) |
| Nom propre, autre que « Immeuble » ou « Maison » | 1 103 (59 %) |

## Par arrondissement

| Arrondissement | Monuments | Prêts | Avec réserve | Pas prêts | Photos (médiane) | Article Wikipédia |
|---|---|---|---|---|---|---|
| 1 | 248 | 237 (96 %) | 7 | 4 | 3 | 76 (31 %) |
| 2 | 114 | 103 (90 %) | 9 | 2 | 5 | 46 (40 %) |
| 3 | 143 | 134 (94 %) | 5 | 4 | 4 | 50 (35 %) |
| 4 | 255 | 242 (95 %) | 6 | 7 | 2 | 82 (32 %) |
| 5 | 108 | 95 (88 %) | 8 | 5 | 3,5 | 51 (47 %) |
| 6 | 196 | 186 (95 %) | 5 | 5 | 3 | 55 (28 %) |
| 7 | 144 | 143 (99 %) | 1 | 0 | 5 | 77 (53 %) |
| 8 | 116 | 110 (95 %) | 6 | 0 | 6 | 65 (56 %) |
| 9 | 129 | 123 (95 %) | 6 | 0 | 3 | 45 (35 %) |
| 10 | 55 | 53 (96 %) | 2 | 0 | 8 | 41 (75 %) |
| 11 | 46 | 42 (91 %) | 4 | 0 | 9 | 30 (65 %) |
| 12 | 32 | 25 (78 %) | 7 | 0 | 9,5 | 23 (72 %) |
| 13 | 24 | 20 (83 %) | 4 | 0 | 12 | 17 (71 %) |
| 14 | 63 | 52 (83 %) | 10 | 1 | 5 | 36 (57 %) |
| 15 | 28 | 27 (96 %) | 1 | 0 | 2 | 12 (43 %) |
| 16 | 75 | 65 (87 %) | 10 | 0 | 7 | 44 (59 %) |
| 17 | 24 | 20 (83 %) | 4 | 0 | 8 | 18 (75 %) |
| 18 | 34 | 29 (85 %) | 5 | 0 | 7,5 | 25 (74 %) |
| 19 | 25 | 21 (84 %) | 4 | 0 | 9 | 19 (76 %) |
| 20 | 19 | 14 (74 %) | 5 | 0 | 7 | 18 (95 %) |

## Par type de monument

Les 12 types les plus fréquents, puis tous les autres.

| Type | Monuments | Prêts | Avec réserve | Pas prêts | Photos (médiane) | Article Wikipédia |
|---|---|---|---|---|---|---|
| immeuble | 710 | 706 (99 %) | 1 | 3 | 2 | 71 (10 %) |
| hôtel | 353 | 351 (99 %) | 1 | 1 | 6 | 241 (68 %) |
| maison | 100 | 98 (98 %) | 2 | 0 | 3 | 25 (25 %) |
| magasin de commerce | 90 | 89 (99 %) | 1 | 0 | 2 | 5 (6 %) |
| station de métro | 68 | 28 (41 %) | 40 | 0 | 5 | 64 (94 %) |
| église | 58 | 57 (98 %) | 0 | 1 | 15 | 55 (95 %) |
| théâtre | 38 | 38 (100 %) | 0 | 0 | 13,5 | 37 (97 %) |
| fontaine | 26 | 12 (46 %) | 14 | 0 | 14 | 25 (96 %) |
| fortification d'agglomération | 21 | 1 (5 %) | 0 | 20 | 2 | 2 (10 %) |
| restaurant | 19 | 19 (100 %) | 0 | 0 | 6 | 12 (63 %) |
| passage couvert | 16 | 4 (25 %) | 12 | 0 | 15 | 16 (100 %) |
| café | 15 | 15 (100 %) | 0 | 0 | 2 | 5 (33 %) |
| autres | 364 | 323 (89 %) | 38 | 3 | 13 | 272 (75 %) |

## Fiabilité des étapes

Les rapprochements sont des jointures exactes sur un identifiant,
contrôlées par la distance et le nom. Les autres étapes ont été mesurées
sur un échantillon vérifié à la main. Le détail et les limites sont dans
`pipeline/README.md`.

| Étape | Mesure | Résultat |
|---|---|---|
| Rapprochement avec Wikidata | liens confirmés, par les règles ou par une relecture | 1 946 sur 2 004 |
| Rapprochement avec OpenStreetMap | liens confirmés, par les règles ou par une relecture | 2 006 sur 2 170 |
| Bâtiment trouvé autour du point | bon bâtiment quand le point tombe dedans | 262 sur 274 |
| Visibilité depuis la rue | accord avec l'étiquette posée à la main, lot de test | 98 sur 100 |
| Photos de référence | photos gardées qui montrent bien l'extérieur, lot de test | 75 sur 100 |

## Problèmes

La liste complète, monument par monument, est dans
`pipeline/data/processed/quality_problems.csv`.

| Problème | Monuments |
|---|---|
| Sans fiche Wikidata | 10 |
| Repéré par un cercle, faute de contour | 129 |
| Point de référence douteux | 1 |
| Visibilité à trancher | 27 |
| Visible depuis la rue mais sans photo | 55 |

Lignes en attente d'une relecture :

| Fichier de relecture | Lignes |
|---|---|
| Rapprochements douteux | 12 |
| Points de référence douteux | 1 |
| Visibilités à trancher | 27 |
