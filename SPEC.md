# SPEC — App de collection du patrimoine parisien (nom de code : « Lutèce »)

> Document de référence pour démarrer le développement avec Claude Code.
> Auteur : Nathan. Langue du projet : français pour la doc et l'UI, anglais pour le code (identifiants, commentaires, commits).

---

## 0. Instructions pour Claude Code (à lire en premier)

- **Travailler phase par phase** (section 9). Ne jamais attaquer une phase sans que la précédente soit validée.
- **Avant d'écrire du code**, proposer un plan court pour la tâche en cours (fichiers créés/modifiés, dépendances ajoutées, choix techniques) et **attendre ma validation**.
- **Petits changements ciblés** : un sujet par modification, pas de refactor non demandé.
- **Demander avant d'ajouter une dépendance** non listée dans ce document.
- Vérifier les versions actuelles des librairies (Expo SDK, etc.) au moment de l'installation plutôt que de supposer ; ce document ne fige volontairement aucune version.
- TypeScript en mode `strict` côté app ; Python typé (type hints) côté pipeline.
- Quand une information de ce document semble fausse ou datée (format d'une API, nom d'un champ), le signaler plutôt que de contourner silencieusement.

---

## 1. Concept

Une app iOS (Android plus tard) qui transforme Paris en terrain de jeu : on se balade, on repère un monument historique, on le **photographie pour le « capturer »** et l'ajouter à sa collection. Chaque capture débloque la **fiche histoire** du lieu. Inspiration : Flash Invaders, appliqué au patrimoine réel.

**Objectifs**
1. Encourager la marche et l'exploration de quartiers moins connus.
2. Raconter l'histoire des lieux, y compris la « longue traîne » (façades, fontaines, hôtels particuliers) que Google Lens ignore.
3. Servir de **projet de data science** présentable en master : construction d'une base patrimoniale unifiée, système d'identification évalué rigoureusement, score de rareté fondé sur les données.

**Hors périmètre v1** : Android, mode social avancé (amis, chat), AR, monuments hors Paris intra‑muros.

---

## 2. Boucle de jeu

1. **Carte** : on voit les monuments autour de soi. Non capturés = silhouettes / pins grisés ; capturés = en couleur.
2. **Capture** : on vise le monument avec l'appareil photo, on déclenche.
3. **Identification** : l'app combine position + orientation + photo pour déterminer le monument (section 6).
4. **Récompense** : animation de capture, haptique, points selon la rareté, fiche histoire débloquée.
5. **Progression** :
   - complétion par **arrondissement** (« 12e : 23/41 ») ;
   - **séries** thématiques (ex. entrées de métro Guimard, hôtels particuliers du Marais, églises, ponts) ;
   - badges (premier lever de soleil, 10 km marchés, tous les ponts…) ;
   - classement global et par arrondissement.
6. **Rareté data‑driven** : un monument peu connu rapporte plus qu'un monument célèbre (section 5.5), ce qui pousse à explorer.

Règles :
- Un monument ne se capture qu'**une fois** par utilisateur.
- Capture uniquement **sur place** (validation serveur de la position).
- Les monuments **non visibles depuis l'espace public** (protection d'intérieur, cour privée fermée) ne sont pas capturables ; ils restent consultables en lecture seule.

---

## 3. Architecture générale

```
┌────────────────────────── App iOS (Expo / React Native) ──────────────────────────┐
│  Carte · Caméra · Boussole · Collection · Fiches                                   │
│  ┌──────────────┐   ┌──────────────────────┐   ┌───────────────────────────────┐  │
│  │ Bundle local │   │ Filtre géométrique   │   │ Encodeur d'image on-device    │  │
│  │ SQLite :     │──▶│ GPS + cap + emprises │──▶│ (ONNX, DINOv2-S) → embedding  │  │
│  │ monuments,   │   │ → 1 à 5 candidats    │   │ comparaison cosinus avec les  │  │
│  │ emprises,    │   └──────────────────────┘   │ embeddings de référence       │  │
│  │ embeddings   │                              └───────────────┬───────────────┘  │
│  └──────▲───────┘                                              │ capture proposée │
└─────────┼──────────────────────────────────────────────────────┼──────────────────┘
          │ téléchargement du bundle versionné                    │ POST capture
┌─────────┴──────────────── Supabase ───────────────────────────────▼─────────────────┐
│  Postgres + PostGIS + pgvector · Auth (Apple, e-mail) · Storage · Edge Functions    │
│  validate-capture (anti-triche) · leaderboard · publication du bundle               │
└─────────▲───────────────────────────────────────────────────────────────────────────┘
          │ chargement des données
┌─────────┴──────────── Pipeline de données (Python, hors ligne) ─────────────────────┐
│  Mérimée → Wikidata → OSM/BD TOPO → Wikimedia Commons → nettoyage + appariement     │
│  → textes → rareté → embeddings de référence → export bundle + chargement Postgres  │
└─────────────────────────────────────────────────────────────────────────────────────┘
          │
┌─────────┴──────────── Évaluation (Python, notebooks) ───────────────────────────────┐
│  Jeu de test terrain · ablations · calibration · rapport méthodologique            │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Principe clé : l'identification se fait sur le téléphone.** Paris compte de l'ordre de 2 000 monuments protégés ; avec ~8 photos de référence par monument et des embeddings de 384 dimensions en float16, la totalité tient en ~12 Mo. Tout le bundle (monuments + emprises simplifiées + embeddings) peut donc être téléchargé une fois et fonctionner **hors ligne**, rapidement, sans coût serveur par photo. Le serveur ne sert qu'à l'authentification, la synchronisation de la collection, l'anti‑triche et les classements.

---

## 4. Stack technique

### App mobile
| Besoin | Outil | Remarque |
|---|---|---|
| Framework | **Expo (React Native, TypeScript)** + **Expo Router** | Réutilise mes compétences React/TS. Nécessite un *development build* (pas Expo Go) à cause du module ONNX. |
| Build / distribution | **EAS Build**, **EAS Submit**, TestFlight | Compte Apple Developer requis. |
| Carte | `react-native-maps` (Apple Maps) en v1 ; `@maplibre/maplibre-react-native` en option pour un style de carte personnalisé | Apple Maps = gratuit, aucune tuile à héberger. |
| Caméra | `expo-camera` | |
| Position + cap | `expo-location` (`watchPositionAsync`, `watchHeadingAsync`) | Utiliser `trueHeading` et son `accuracy`. |
| Inférence image | `onnxruntime-react-native` (Core ML execution provider sur iOS) | Alternative : `react-native-fast-tflite`. |
| Prétraitement image | `expo-image-manipulator` (redimensionnement / recadrage 224×224) | Normalisation des pixels en TS. |
| Stockage local | `expo-sqlite` (bundle + collection hors ligne) | |
| État | Zustand (état UI) + TanStack Query (données serveur) | |
| Animations / ressenti | `react-native-reanimated`, `expo-haptics` | Le moment de capture doit être gratifiant. |
| Styles | NativeWind (Tailwind pour RN) | À confirmer. |
| Backend client | `@supabase/supabase-js` | |

### Backend
| Besoin | Outil |
|---|---|
| Base de données | **Supabase Postgres** avec extensions **PostGIS** et **pgvector** |
| Auth | Supabase Auth : **Sign in with Apple** (obligatoire sur l'App Store si un login tiers est proposé) + lien magique par e‑mail |
| Logique serveur | Supabase **Edge Functions** (TypeScript / Deno) |
| Fichiers | Supabase Storage (bundle versionné, photos de référence) |
| Analytics (optionnel) | PostHog hébergé en UE, avec consentement |

### Pipeline et évaluation (Python)
- Gestion d'environnement : **uv**
- Données : **polars** ou pandas, **geopandas**, **shapely**, **pyproj**
- Requêtes : `requests` / `httpx`, `SPARQLWrapper` (Wikidata), Overpass API (OSM)
- Appariement : `rapidfuzz` (noms), jointures spatiales geopandas
- Modèles : **PyTorch**, `transformers` ou `timm` (DINOv2), export **ONNX** (`torch.onnx`, `onnxruntime`, quantification `onnxruntime.quantization`)
- Évaluation : `scikit-learn` (métriques, calibration, régression logistique), notebooks Jupyter
- Base : `psycopg` pour charger Postgres
- Qualité : `ruff`, `pytest`

---

## 5. Données — construction de la base patrimoniale

C'est le **cœur data science** du projet. Toutes les étapes vivent dans `pipeline/`, sont rejouables, et produisent un **rapport de qualité** (taux d'appariement, champs manquants, cas ambigus).

### 5.1 Sources

| Source | Contenu | Licence |
|---|---|---|
| **Base Mérimée** (ministère de la Culture ; jeu « immeubles protégés au titre des monuments historiques » sur data.culture.gouv.fr / plateforme POP) | Liste officielle : identifiant `PA…`, nom, adresse, dates, auteurs, statut (classé/inscrit), description de la protection, parfois coordonnées | Licence Ouverte Etalab |
| **Wikidata** | Pivot : propriété **P380** (identifiant Mérimée), **P625** (coordonnées), **P373** (catégorie Commons), liens Wikipedia, architecte, date | CC0 |
| **OpenStreetMap** (Overpass) | Emprises des bâtiments, tag **`ref:mhs`** (= identifiant Mérimée en France), `heritage=*` | ODbL (attribution + partage à l'identique de la base dérivée) |
| **BD TOPO (IGN)** | Emprises de bâtiments de référence, hauteurs | Licence Ouverte |
| **Base Adresse Nationale** | Géocodage des adresses Mérimée | Licence Ouverte |
| **Wikipedia FR** | Textes historiques des monuments connus | CC BY‑SA 4.0 |
| **Wikimedia Commons** (dont Wiki Loves Monuments) | Photos de référence, souvent taguées avec l'identifiant Mérimée | Licence propre à chaque fichier (à stocker) |
| **Paris Musées / Gallica** (v2) | Photos anciennes et gravures pour un mode « avant / après » | Variable, souvent domaine public |

> Vérifier à l'ingestion le format exact de chaque source (noms de champs, pagination) et documenter tout écart dans `pipeline/README.md`.

### 5.2 Étapes du pipeline

1. **`ingest_merimee`** : extraire les notices de Paris (département 75). Normaliser les champs.
2. **`ingest_wikidata`** : requête SPARQL de tous les items ayant un P380 situés à Paris. Exemple de départ :
   ```sparql
   SELECT ?item ?itemLabel ?merimee ?coord ?commonsCat ?article WHERE {
     ?item wdt:P380 ?merimee ;
           wdt:P131* wd:Q90 .
     OPTIONAL { ?item wdt:P625 ?coord }
     OPTIONAL { ?item wdt:P373 ?commonsCat }
     OPTIONAL { ?article schema:about ?item ;
                         schema:isPartOf <https://fr.wikipedia.org/> }
     SERVICE wikibase:label { bd:serviceParam wikibase:language "fr". }
   }
   ```
3. **`ingest_osm`** : via Overpass, tous les objets portant `ref:mhs` dans Paris (`out geom`), plus les emprises des bâtiments autour.
4. **`resolve_entities`** : relier Mérimée ↔ Wikidata ↔ OSM.
   - Jointure exacte sur l'identifiant Mérimée quand il existe.
   - Sinon : appariement par distance spatiale + similarité de nom (rapidfuzz), avec score de confiance.
   - Cas ambigus exportés dans un CSV pour revue manuelle.
5. **`geometry`** : pour chaque monument, déterminer **un point de référence** et **une emprise** (polygone OSM ou BD TOPO, sinon tampon autour du point). Simplifier les polygones pour l'app.
6. **`visibility`** : classer chaque monument `visible` / `non_visible` / `inconnu` depuis l'espace public (heuristiques sur le texte de protection : « décor intérieur », « escalier », « cour »… + revue manuelle des cas douteux).
7. **`ingest_commons`** : récupérer les photos de référence (catégorie P373, fichiers portant le modèle Mérimée). Garder auteur, licence, URL, dimensions. Filtrer : extérieur, résolution suffisante, pas de gros plan de détail. Objectif : 5 à 15 photos par monument, avec des angles variés.
8. **`texts`** : construire la fiche de chaque monument (section 5.4).
9. **`rarity`** : calculer le score de rareté (section 5.5).
10. **`embeddings`** : calculer les embeddings de référence avec le modèle retenu (section 6).
11. **`export`** : produire le bundle SQLite versionné pour l'app + charger Postgres.
12. **`quality_report`** : statistiques de couverture et liste des problèmes.

### 5.3 Modèle de données (Postgres)

```sql
-- extensions : postgis, vector

monuments (
  id               uuid primary key,
  merimee_id       text unique,          -- PA00088xxx
  wikidata_qid     text,
  osm_id           text,
  name             text not null,
  arrondissement   smallint,
  location         geography(point, 4326) not null,
  footprint        geography(polygon, 4326),
  category         text,                 -- église, hôtel particulier, fontaine, pont…
  period_start     smallint,             -- siècle ou année
  architects       text[],
  protection       text,                 -- classé / inscrit
  protection_desc  text,
  visibility       text,                 -- visible | non_visible | inconnu
  rarity_score     real,
  rarity_tier      text,                 -- commun | peu_commun | rare | légendaire
  summary_fr       text,                 -- 2-3 phrases
  story_fr         text,                 -- fiche longue
  sources          jsonb,                -- [{label, url, licence}]
  data_version     int
)

reference_images (
  id           uuid primary key,
  monument_id  uuid references monuments,
  source_url   text,
  author       text,
  licence      text,
  embedding    vector(384),
  is_user_contributed boolean default false
)

series (id, slug, name, description)
monument_series (monument_id, series_id)

profiles (id uuid references auth.users, username, created_at)

captures (
  id              uuid primary key,
  user_id         uuid references auth.users,
  monument_id     uuid references monuments,
  captured_at     timestamptz,
  lat, lon        double precision,
  gps_accuracy_m  real,
  heading_deg     real,
  heading_accuracy_deg real,
  geo_score       real,
  image_score     real,
  final_score     real,
  status          text,                  -- accepted | pending_review | rejected
  unique (user_id, monument_id)
)

achievements (id, slug, name, rule jsonb)
user_achievements (user_id, achievement_id, unlocked_at)
```

Row Level Security activée partout : un utilisateur ne lit/écrit que ses propres captures ; `monuments`, `series`, `reference_images` en lecture publique.

### 5.4 Fiches histoire

- Sources prioritaires : notice Mérimée (faits datés et vérifiables), article Wikipedia FR, autres sources ouvertes.
- Format : `summary_fr` (2–3 phrases, affiché à la capture) + `story_fr` (fiche longue, 150–400 mots) + bloc **« Le saviez‑vous ? »** + **sources citées**.
- Rédaction assistée par LLM **dans le pipeline, hors ligne** (jamais dans l'app) : le modèle reformule uniquement à partir des sources fournies, puis **relecture humaine** pour les monuments publiés. Stocker les sources pour chaque fiche.
- Les textes dérivés de Wikipedia sont sous **CC BY‑SA** : attribution obligatoire et partage à l'identique de ces textes ; afficher les crédits dans chaque fiche.
- Les monuments sans texte suffisant reçoivent une fiche minimale (nom, date, architecte, protection) marquée « à enrichir ».

### 5.5 Score de rareté

Mesure de la notoriété d'un monument, inversée pour donner plus de points aux lieux méconnus :
- vues annuelles de la page Wikipedia (API Wikimedia pageviews) ;
- nombre de photos sur Commons ;
- présence dans des guides ou listes de lieux touristiques (optionnel).

Combiner en un indice (rangs ou z‑scores en log), puis découper en paliers (`commun`, `peu_commun`, `rare`, `légendaire`) avec des points associés. Documenter la méthode et vérifier sa cohérence à la main sur un échantillon.

---

## 6. Reconnaissance d'image — recommandation

### 6.1 Choix retenu : géométrie d'abord, image pour départager

L'identification se fait en **deux étages** :

1. **Filtre géométrique (sans IA)** : avec la position GPS, sa précision et le cap de la boussole, on calcule quels monuments sont **dans le champ de vision** :
   - monuments dont l'emprise est à moins de `R = clamp(2 × précision_gps, 50 m, 150 m)` ;
   - dont la direction (bearing) depuis l'utilisateur vers le point le plus proche de l'emprise tombe dans le cône `cap ± (30° + précision_cap)` ;
   - score géométrique `geo_score` décroissant avec la distance et l'écart d'angle.
   → En pratique, il reste **1 à 5 candidats**.
2. **Comparaison d'images** : la photo est transformée en vecteur (embedding) par un modèle de vision **exécuté sur le téléphone**, puis comparée par similarité cosinus aux photos de référence des seuls candidats. `image_score` = similarité maximale par monument.

Décision : `final_score = f(geo_score, image_score)`. En v1, combinaison pondérée simple ; à terme, **régression logistique apprise sur le jeu d'évaluation** (section 8), ce qui donne une probabilité calibrée.
- Score élevé et écart net avec le 2e candidat → **capture acceptée**.
- Ambiguïté entre 2–3 candidats → l'app demande « C'est lequel ? » avec vignettes ; la réponse est enregistrée comme étiquette (utile pour améliorer le modèle).
- Aucun candidat convaincant → message d'échec bienveillant (« Rapproche‑toi », « Vise la façade »).

### 6.2 Quel modèle d'image ?

**Recommandation : DINOv2 ViT‑S/14** (Meta, **licence Apache 2.0**, ~22 M de paramètres, embeddings de 384 dimensions).
- Il est réputé très performant pour la **recherche d'instances** (retrouver *le même objet* sous un autre angle), ce qui correspond exactement au besoin, mieux que les modèles entraînés à associer images et texte.
- Exporté en ONNX et quantifié (float16 ou int8), il pèse ~20–45 Mo et tourne en quelques dizaines de millisecondes sur un iPhone récent.
- Aucun entraînement n'est nécessaire en v1 : on utilise le modèle tel quel (« zero‑shot retrieval »).

**Alternatives à comparer dans l'évaluation** (c'est une partie intéressante du rapport) :
| Option | Pour | Contre |
|---|---|---|
| **SigLIP** (Google, Apache 2.0) | Bon encodeur généraliste, permet aussi des requêtes texte | Moins ciblé sur la recherche d'instances |
| **Apple Vision `VNGenerateImageFeaturePrintRequest`** | Intégré à iOS, aucun modèle à embarquer | iOS uniquement, demande un module natif Expo, qualité à mesurer |
| **Google Cloud Vision (détection de monuments)** | Très bon sur les monuments célèbres | Payant, réseau obligatoire, aveugle sur la longue traîne → utile seulement comme **référence de comparaison** |
| **LLM multimodal (Claude, GPT…)** | Peut décrire n'importe quelle façade | 2–5 s de latence, coût par photo, réseau obligatoire, risque d'erreur assurée sur les lieux obscurs → **déconseillé comme moteur principal** |

**Améliorations possibles en v2** : affiner DINOv2 sur les photos de Paris (apprentissage contrastif), ajouter les photos validées des utilisateurs comme références (après modération), tester un modèle spécialisé « landmark retrieval » entraîné sur Google Landmarks v2.

### 6.3 Points d'attention
- **Écart de domaine** : les photos Commons sont souvent belles, de face, en plein jour ; les photos utilisateurs seront de biais, de nuit, avec des passants ou des échafaudages. Diversifier les références et mesurer l'effet.
- **Boussole imprécise** en ville (perturbations magnétiques, ±10–20°) : utiliser la précision renvoyée et élargir le cône en conséquence.
- **Monuments sans photo de référence** : capture possible uniquement en géométrie stricte (≤ 30 m) + confirmation de l'utilisateur ; la photo devient une référence candidate après modération.
- Le prétraitement image (taille, normalisation, recadrage) doit être **strictement identique** entre le pipeline Python et l'app ; écrire un test qui compare les embeddings des deux côtés sur les mêmes images.

---

## 7. Anti‑triche et confidentialité

### Validation serveur (Edge Function `validate-capture`)
- Distance entre la position déclarée et l'emprise du monument ≤ seuil.
- Vitesse plausible entre deux captures successives (pas de téléportation).
- Limite de captures par minute et par jour.
- Unicité (un monument par utilisateur).
- Les cas limites passent en `pending_review` au lieu d'être rejetés.
- Le score d'image calculé sur le téléphone est enregistré pour audit (non vérifiable côté serveur en v1).

### RGPD et App Store
- La localisation est une donnée personnelle : **pas de suivi continu en arrière‑plan**, position enregistrée seulement au moment d'une capture, consentement explicite.
- **Les photos restent sur le téléphone par défaut** (elles peuvent contenir des passants). Envoi au serveur uniquement si l'utilisateur choisit de contribuer une photo de référence.
- Textes d'autorisation iOS clairs (caméra, localisation « quand l'app est utilisée »).
- Politique de confidentialité et fiche « App Privacy » de l'App Store à rédiger.
- Page « Crédits et licences » dans l'app : Mérimée (Etalab), OSM (ODbL), Wikipedia (CC BY‑SA), auteurs Commons.

---

## 8. Évaluation (volet scientifique)

Objectif : pouvoir dire précisément **à quel point l'identification fonctionne, et pourquoi**.

- **Jeu de test terrain** : 300 à 500 photos prises soi‑même dans Paris (plusieurs arrondissements, jour/nuit, angles variés), chacune avec GPS, cap, précisions et **étiquette vérifiée** du monument. Enregistrées via un **mode « collecte »** caché dans l'app de dev.
- **Métriques** : précision top‑1 et top‑3, taux de fausses captures acceptées, taux de refus à tort, courbes précision / rappel selon le seuil, **calibration** (quand le système dit 80 %, a‑t‑il raison 8 fois sur 10 ?).
- **Ablations** : GPS seul → GPS + cap → GPS + cap + image ; DINOv2 vs SigLIP vs Apple Vision ; nombre de photos de référence par monument.
- **Analyse d'erreurs** : par catégorie de monument, par distance, par précision GPS, par conditions de lumière.
- **Livrable** : rapport méthodologique (format article, 8–15 pages) + notebooks reproductibles.

Extension possible (avec consentement, données agrégées) : la gamification fait‑elle réellement explorer de nouveaux quartiers ? Mesure de la diversité des arrondissements visités dans le temps.

---

## 9. Phases de développement

| Phase | Contenu | Livrable de fin de phase | Durée indicative |
|---|---|---|---|
| **0. Mise en place** | Monorepo, outils, Supabase local, projet Expo vide qui tourne sur iPhone en dev build | App « Hello Paris » sur mon téléphone | 1 semaine |
| **1. Base patrimoniale** | Étapes 1 à 7 du pipeline + rapport de qualité | Table `monuments` remplie, emprises, photos de référence, rapport de couverture | 4–6 semaines |
| **2. MVP app sans IA** | Carte, fiches, auth Apple, capture par **géométrie seule** (GPS + cap), collection, bundle hors ligne | App utilisable sur TestFlight par quelques amis | 4 semaines |
| **3. Reconnaissance d'image** | Export DINOv2 en ONNX, embeddings de référence, intégration on‑device, combinaison des scores, écran « C'est lequel ? » | Capture avec photo fonctionnelle | 3–4 semaines |
| **4. Évaluation** | Mode collecte, jeu de test, ablations, calibration, régression logistique | Notebooks + premiers résultats chiffrés | 3–4 semaines (en parallèle de la phase 5) |
| **5. Gamification** | Rareté, points, séries, badges, arrondissements, classements, animations de capture | Boucle de jeu complète | 3 semaines |
| **6. Fiches et finitions** | Rédaction / relecture des fiches, crédits, onboarding, confidentialité | Version candidate App Store | 2–3 semaines |
| **7. Publication** | EAS Submit, revue Apple, rapport final | App publiée + rapport méthodologique | 2 semaines |

---

## 10. Structure du dépôt

```
lutece/
├── SPEC.md                    # ce document
├── CLAUDE.md                  # conventions courtes pour Claude Code (à créer en phase 0)
├── apps/
│   └── mobile/                # Expo + Expo Router (TypeScript)
│       ├── app/               # écrans (carte, capture, collection, fiche, profil)
│       ├── src/
│       │   ├── features/      # capture/, map/, collection/, monuments/
│       │   ├── recognition/   # géométrie, prétraitement, inférence ONNX, scoring
│       │   ├── db/            # accès SQLite au bundle
│       │   └── lib/           # supabase, utils
│       └── assets/models/     # modèle ONNX
├── supabase/
│   ├── migrations/            # schéma SQL, RLS
│   ├── functions/             # validate-capture, leaderboard…
│   └── seed.sql
├── pipeline/                  # Python (uv)
│   ├── pyproject.toml
│   ├── src/lutece_pipeline/   # une étape = un module
│   ├── data/raw|interim|processed/   # ignoré par git, sauf petits échantillons
│   └── README.md
├── eval/
│   ├── notebooks/
│   └── testset/               # métadonnées du jeu de test (photos hors git)
└── docs/
    └── rapport/               # rapport méthodologique
```

---

## 11. Questions ouvertes (à trancher au fil du projet)

- Nom définitif de l'app et identité visuelle.
- Inclure en v2 du patrimoine non protégé (fontaines Wallace, plaques commémoratives, mobilier urbain) via l'open data de la Ville de Paris ?
- Style de carte personnalisé (MapLibre) dès la v1 ou plus tard ?
- Modération des photos contribuées : manuelle seulement, ou assistée ?
- Monétisation éventuelle (aucune en v1).

---

## 12. Première tâche pour Claude Code

Phase 0 uniquement :
1. Proposer la structure du monorepo et les commandes d'initialisation (Expo avec Expo Router et TypeScript strict, projet Python avec uv, Supabase CLI).
2. Proposer un `CLAUDE.md` court (conventions, commandes utiles).
3. **Attendre ma validation**, puis créer le squelette.
4. Ensuite seulement, proposer le plan de la phase 1, en commençant par `ingest_merimee`.
