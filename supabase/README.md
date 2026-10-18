# Supabase

Le serveur de Lutèce. Le schéma ne change que par `migrations/` (voir `CLAUDE.md`).

## Contributions (phase 4)

Les joueurs qui le veulent envoient leurs photos, avec ce que l'app savait au
moment de la photo, pour mesurer et améliorer la reconnaissance.

- **Dans l'app** : l'écran « Contribuer » (en bas de la Collection, et depuis
  le mode collecte) explique ce qui part et porte l'interrupteur, éteint par
  défaut. Une fois allumé, chaque photo de capture ou du mode collecte part
  une fois, y compris celles déjà prises, réduite à 1 600 px ; ce qui échoue
  (pas de réseau) repart au retour dans l'app. « Supprimer mes contributions »
  efface tout du serveur et éteint l'interrupteur.
- **Sans compte** : connexion anonyme de Supabase Auth. L'identifiant reste sur
  le téléphone ; si le joueur supprime l'app, il ne peut plus effacer ses
  photos lui-même.
- **Table `contributions`** : une ligne par photo, de l'identifiant de
  l'échantillon ou de la capture sur le téléphone (un envoi en double est
  refusé). Mêmes informations que le jeu de test terrain
  (`eval/testset/README.md`) : position, cap, candidats, décision, monument,
  vecteur de la photo, versions, et la version du texte accepté
  (`CONSENT_VERSION` dans `apps/mobile/src/features/contribute/rows.ts`).
- **Photos** : bucket privé `contributions`, JPEG de 1 Mo au plus, un dossier
  par joueur.
- **Accès** : chaque joueur n'atteint que ses lignes et son dossier, pour
  ajouter ou supprimer (RLS) ; il ne modifie rien. Tout lire demande la clé
  secrète, hors de l'app : le tableau de bord (Table Editor, Storage) ou un
  script.

Un nouveau texte de consentement : changer `CONSENT_VERSION`. Les joueurs
retrouvent alors l'interrupteur éteint et relisent le texte avant de rallumer.

## Classements (phase 5)

Les joueurs qui le veulent comparent leurs points, pour tout Paris et par
arrondissement, sous un pseudonyme.

- **Dans l'app** : l'écran « Classement », depuis la Collection. La première
  fois, il explique ce qui part et qui voit quoi, et demande un pseudonyme
  (3 à 20 caractères, unique sans tenir compte des majuscules). Ensuite,
  chaque capture part une fois, dans l'ordre, y compris celles faites avant
  l'inscription ; ce qui échoue repart au retour dans l'app. « Quitter les
  classements » efface le profil et, avec lui, les captures.
- **`places`** : les 394 lieux de l'app (contour, distance de capture,
  arrondissement, rareté), que le serveur lit pour vérifier une capture.
  Le pipeline les écrit dans `seeds/places.sql`
  (`uv run python -m lutece_pipeline.export_places`) ; `supabase db push
  --include-seed` les envoie au projet hébergé, sans mot de passe. Un lieu
  qui quitte le fichier embarqué reste sur le serveur.
- **`profiles`** et **`captures`** (SPEC §5.3) : chaque joueur ne lit et ne
  supprime que son profil et ses captures. Il n'ajoute une capture que par
  la fonction `submit_capture`, qui la vérifie et lui donne ses points
  d'après la rareté du lieu sur le serveur :
  - refusée si sa date est dans le futur, ou si la position est à plus du
    double de la portée (le plus grand de la distance de capture du lieu et
    de 150 m, plus la précision du GPS jusqu'à 100 m) ;
  - en attente au-delà de la portée, au-dessus de 60 km/h depuis la capture
    précédente, ou au-delà de 30 captures dans la journée ;
  - acceptée sinon. Seuils provisoires (décision du 19 octobre 2026).
  Une capture en attente ne compte qu'une fois validée à la main : passer son
  `status` à `accepted` dans le tableau de bord (Table Editor, `captures`).
- **`leaderboard(in_arrondissement, size)`** ne renvoie que le rang, le
  pseudonyme, les points et le nombre de captures acceptées, et toujours la
  ligne du joueur qui demande. Les autres joueurs ne voient jamais où ni quand.

Un nouveau texte d'inscription : changer `LEADERBOARD_CONSENT_VERSION`
(`apps/mobile/src/features/ranking/send.ts`).

## Brancher l'app

L'app lit l'URL du projet et sa clé publiable dans `apps/mobile/.env` (modèle
dans `.env.example`, jamais dans git). Sans ces deux valeurs, l'app n'envoie
rien et l'écran « Contribuer » n'apparaît pas. La clé secrète et le mot de
passe de la base ne vont jamais dans l'app.

## Commandes

| Commande | Rôle |
|---|---|
| `supabase test db` | tests des droits (pgTAP, `tests/database/`) sur la pile locale |
| `supabase db push` | appliquer les migrations au projet hébergé (lié par `supabase link`) |
| `supabase db push --include-seed` | y envoyer aussi les lieux de `seeds/places.sql` |

## Écarts au SPEC

- **Vérification des captures** : le SPEC (§7) prévoit une Edge Function
  `validate-capture`. Une fonction de la base, `submit_capture`, fait les
  mêmes contrôles en une seule opération, se teste comme le reste et n'a pas
  de service à déployer.
- **Lieux des captures** : la table `monuments` du SPEC exige une notice
  Mérimée ; les captures renvoient à `places`, qui tient aussi les lieux non
  protégés.

- **Connexion anonyme** : le SPEC prévoit Sign in with Apple et le lien
  magique (§4) pour les comptes de la phase 5. Contribuer ne demande pas de
  compte : la connexion anonyme suffit, et un compte pourra la reprendre plus
  tard.
- **Contribution en bloc** : le SPEC (§7) envoie une photo seulement si le
  joueur choisit de la contribuer comme photo de référence. Ici, le joueur
  accepte une fois pour toutes ses photos, pour mesurer la reconnaissance sur
  des photos de terrain ; elles ne deviennent pas des photos de référence
  sans tri.
