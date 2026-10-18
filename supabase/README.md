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

## Écarts au SPEC

- **Connexion anonyme** : le SPEC prévoit Sign in with Apple et le lien
  magique (§4) pour les comptes de la phase 5. Contribuer ne demande pas de
  compte : la connexion anonyme suffit, et un compte pourra la reprendre plus
  tard.
- **Contribution en bloc** : le SPEC (§7) envoie une photo seulement si le
  joueur choisit de la contribuer comme photo de référence. Ici, le joueur
  accepte une fois pour toutes ses photos, pour mesurer la reconnaissance sur
  des photos de terrain ; elles ne deviennent pas des photos de référence
  sans tri.
