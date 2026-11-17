import { useRouter } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet } from 'react-native';

import { formatCount } from '@/lib/format';
import { useTheme } from '@/lib/theme';

import { Lead, Part, SourceRow } from './Prose';

const MONUMENTS = [
  {
    name: 'Base Mérimée',
    what: 'Ministère de la Culture : la liste des monuments historiques et leurs notices.',
    licence: 'Licence Ouverte 2.0',
    url: 'https://pop.culture.gouv.fr',
  },
  {
    name: 'OpenStreetMap',
    what: '© les contributeurs d’OpenStreetMap : les contours des bâtiments.',
    licence: 'ODbL',
    url: 'https://www.openstreetmap.org/copyright',
  },
  {
    name: 'Wikidata',
    what: 'Les liens entre les sources, les noms des lieux et leurs dates.',
    licence: 'CC0',
    url: 'https://www.wikidata.org',
  },
  {
    name: 'Wikipédia',
    what: 'Les fiches sont rédigées à partir des articles de Wikipédia et des notices Mérimée. Les textes tirés de Wikipédia sont sous la même licence.',
    licence: 'CC BY-SA 4.0',
    url: 'https://creativecommons.org/licenses/by-sa/4.0/deed.fr',
  },
];

const TOOLS = [
  {
    name: 'DINOv2',
    what: 'Meta AI : le modèle qui compare votre photo aux photos de référence, sur le téléphone.',
    licence: 'Apache 2.0',
    url: 'https://github.com/facebookresearch/dinov2',
  },
  {
    name: 'Plans',
    what: 'Apple : le fond de la carte.',
    url: 'https://www.apple.com/legal/internet-services/maps/',
  },
  {
    name: 'Playfair Display',
    what: 'Claus Eggers Sørensen : la police des titres.',
    licence: 'SIL OFL 1.1',
    url: 'https://fonts.google.com/specimen/Playfair+Display',
  },
  {
    name: 'Inter',
    what: 'Rasmus Andersson : la police du texte.',
    licence: 'SIL OFL 1.1',
    url: 'https://rsms.me/inter/',
  },
];

const SOFTWARE = {
  name: 'Code source de Lutèce',
  what: 'Construite avec Expo, React Native et d’autres bibliothèques libres (licences MIT, Apache 2.0 ou BSD).',
  url: 'https://github.com/NathanTessot75/lutece',
};

/** Where the places, texts, photos, model and letters of Lutèce come from. */
export function Credits() {
  const theme = useTheme();
  const router = useRouter();
  const db = useSQLiteContext();
  const [photos, setPhotos] = useState<{ photos: number; authors: number } | null>(null);

  useEffect(() => {
    void db
      .getFirstAsync<{ photos: number; authors: number }>(
        'select count(*) as photos, count(distinct author) as authors from photos',
      )
      .then(setPhotos);
  }, [db]);

  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
    >
      <Lead>
        Lutèce repose sur des données ouvertes et des logiciels libres. Merci à celles et ceux qui
        les font vivre.
      </Lead>

      <Part title="Les monuments">
        {MONUMENTS.map((source) => (
          <SourceRow key={source.name} source={source} />
        ))}
      </Part>

      <Part title="Les photos">
        <SourceRow
          source={{
            name: 'Wikimedia Commons',
            what: `Les photos qui servent à reconnaître les monuments${
              photos === null
                ? ''
                : ` : ${formatCount(photos.photos)} photos de ${formatCount(photos.authors)} auteurs`
            }, sous licences libres. Leurs auteurs, lieu par lieu.`,
          }}
          onPress={() => router.push('/photo-credits')}
        />
      </Part>

      <Part title="La reconnaissance, la carte et les lettres">
        {TOOLS.map((source) => (
          <SourceRow key={source.name} source={source} />
        ))}
      </Part>

      <Part title="Le logiciel">
        <SourceRow source={SOFTWARE} />
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
