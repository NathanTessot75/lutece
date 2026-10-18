# Jeu de test terrain

Photos prises dans Paris avec le mode collecte de l'app (`lutece://collect`),
chacune avec ce que l'app savait au moment de la photo et le monument qu'elle
montre, indiqué par le photographe (SPEC §8).

`uv run python -m lutece_pipeline.pull_field_samples`, dans `pipeline/`, copie
tout depuis l'iPhone et réécrit les fichiers :

- `samples.csv` : une ligne par photo (heure en UTC, position et précision du
  GPS, cap et niveau de la boussole, fichier de la photo, monument étiqueté ou
  aucun, cases « de biais » et « en partie caché », décision qu'aurait prise
  l'app et sa raison, versions du fichier embarqué, du modèle et de l'app) ;
- `candidates.csv` : une ligne par photo et par monument à portée (distance,
  angle à tourner, dans l'axe ou non, score géométrique, ressemblance de la
  photo avec ses photos de référence) ;
- `photos/` : les photos, réduites à 1 600 px de côté. Elles ne vont pas dans
  git : elles peuvent montrer des passants.

Les identifiants des monuments sont ceux du fichier embarqué dans l'app
(`apps/mobile/assets/data/lutece.db`). Le détail est dans le README du
pipeline, section « Jeu de test terrain ».
