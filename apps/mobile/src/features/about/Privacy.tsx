import { useRouter } from 'expo-router';
import { ScrollView, StyleSheet } from 'react-native';

import { useContribution } from '@/features/contribute/ContributeProvider';
import { useRanking } from '@/features/ranking/RankingProvider';
import { useTheme } from '@/lib/theme';

import { Lead, Paragraph, Part, SourceRow } from './Prose';

/** What Lutèce does with the data of the player, and what it never does. */
export function Privacy() {
  const theme = useTheme();
  const router = useRouter();
  const ranking = useRanking();
  const contribution = useContribution();
  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
    >
      <Lead>
        Lutèce se joue sans compte. Par défaut, tout reste sur votre téléphone : rien ne part tant
        que vous ne rejoignez pas les classements ou ne contribuez pas vos photos.
      </Lead>

      <Part title="Sur votre téléphone">
        <Paragraph>
          Votre collection, vos photos, vos badges et vos réglages restent dans l’app. Supprimer
          l’app les efface.
        </Paragraph>
      </Part>

      <Part title="Votre position">
        <Paragraph>
          Lutèce ne lit votre position que lorsque l’app est ouverte : pour la carte, les distances
          et la vérification d’une capture. Elle n’est enregistrée qu’au moment d’une capture, avec
          elle. Aucun suivi en arrière-plan.
        </Paragraph>
      </Part>

      <Part title="La caméra et la boussole">
        <Paragraph>
          La caméra sert à photographier le monument que vous visez, et la boussole à savoir dans
          quelle direction. La reconnaissance du monument se fait sur le téléphone : la photo ne
          part pas pour cela.
        </Paragraph>
      </Part>

      {ranking.available && (
        <Part title="Les classements, si vous les rejoignez">
          <Paragraph>
            Partent votre pseudonyme et, pour chaque capture, le monument, l’heure, votre position
            et ce que Lutèce a mesuré, pour vérifier que vous étiez sur place ; et un nombre tiré au
            hasard qui choisit votre lieu du jour. Les autres joueurs ne voient que votre
            pseudonyme, vos points et votre nombre de captures. Quitter les classements efface tout
            cela du serveur.
          </Paragraph>
          <SourceRow
            source={{
              name: 'Classements',
              what: 'Rejoindre, voir où en sont vos captures, ou quitter.',
            }}
            onPress={() => router.push('/leaderboard')}
          />
        </Part>
      )}

      {contribution.available && (
        <Part title="Vos photos, si vous les contribuez">
          <Paragraph>
            Partent vos photos de capture, réduites, avec l’heure, votre position et votre cap au
            moment de la photo. Seul le développeur de Lutèce les voit, pour améliorer la
            reconnaissance. Vous pouvez arrêter et les supprimer à tout moment.
          </Paragraph>
          <SourceRow
            source={{
              name: 'Contribuer mes photos',
              what: 'Activer, arrêter, ou supprimer vos photos envoyées.',
            }}
            onPress={() => router.push('/contribute')}
          />
        </Part>
      )}

      {(ranking.available || contribution.available) && (
        <Part title="Où vont ces données">
          <Paragraph>
            Sur un serveur Supabase en Europe, à Paris. Un identifiant anonyme, sans nom ni adresse
            e-mail, relie vos envois à ce téléphone.
          </Paragraph>
        </Part>
      )}

      <Part title="Les autres services">
        <Paragraph>
          La carte vient d’Apple Plans et certaines photos de référence s’affichent depuis
          Wikimedia Commons : comme pour un site web, ces services reçoivent alors les demandes de
          votre téléphone.
        </Paragraph>
      </Part>

      <Part title="Ce que Lutèce ne fait pas">
        <Paragraph>
          Pas de publicité, pas de mesure d’audience, pas de suivi d’une app à l’autre, et aucune
          donnée vendue ni partagée.
        </Paragraph>
      </Part>

      <Part title="Une question ?">
        <Paragraph>
          Écrivez au développeur de Lutèce sur la page GitHub du projet, en ouvrant un ticket. Les
          tickets sont publics : n’y mettez pas d’informations personnelles.
        </Paragraph>
        <SourceRow
          source={{
            name: 'Lutèce sur GitHub',
            what: 'Ouvrir un ticket pour poser une question ou signaler un problème.',
            url: 'https://github.com/NathanTessot75/lutece/issues',
          }}
        />
      </Part>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: 16,
    paddingBottom: 40,
    gap: 10,
  },
});
