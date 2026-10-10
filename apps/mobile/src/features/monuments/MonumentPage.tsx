import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import type { MonumentDetails, MonumentPhoto } from '@/db/monuments';
import { capitalize, formatArrondissement, formatCentury } from '@/lib/format';
import { type Theme, useTheme } from '@/lib/theme';

import { PhotoCarousel } from './PhotoCarousel';

// A notice may list several addresses, separated this way.
const ADDRESS_SEPARATOR = ';';

type Fact = { label: string; value: string };
type Source = { label: string; url: string };

function listFacts(monument: MonumentDetails): Fact[] {
  const facts: Fact[] = [];
  if (monument.category) {
    facts.push({ label: 'Genre', value: capitalize(monument.category) });
  }
  if (monument.century) {
    facts.push({ label: 'Époque', value: formatCentury(monument.century) });
  }
  if (monument.architects.length > 0) {
    facts.push({
      label: monument.architects.length > 1 ? 'Architectes' : 'Architecte',
      value: monument.architects.join(', '),
    });
  }
  facts.push({
    label: 'Protection',
    value: `${capitalize(monument.protection)} au titre des monuments historiques`,
  });
  return facts;
}

function listSources(monument: MonumentDetails): Source[] {
  const sources = [
    {
      label: 'Notice Mérimée (ministère de la Culture)',
      url: `https://pop.culture.gouv.fr/notice/merimee/${monument.merimeeId}`,
    },
  ];
  if (monument.wikidataQid) {
    sources.push({
      label: 'Wikidata',
      url: `https://www.wikidata.org/wiki/${monument.wikidataQid}`,
    });
  }
  return sources;
}

function describeLocation(monument: MonumentDetails): string[] {
  const lines = (monument.address ?? '')
    .split(ADDRESS_SEPARATOR)
    .map((address) => address.trim())
    .filter(Boolean);
  if (monument.arrondissement !== null) {
    lines.push(`Paris, ${formatArrondissement(monument.arrondissement)}`);
  }
  return lines;
}

/** Whether the monument can be captured, and why not when it cannot. */
function describeStatus(monument: MonumentDetails): string {
  if (monument.readiness !== 'not_ready') {
    return 'Peut être capturé';
  }
  return monument.visibility === 'non_visible'
    ? 'Consultation seule : ne se voit pas depuis la rue'
    : 'Consultation seule : visibilité à vérifier';
}

function Section({ title, theme }: { title: string; theme: Theme }) {
  return <Text style={[styles.section, { color: theme.secondaryText }]}>{title}</Text>;
}

type Props = {
  monument: MonumentDetails;
  photos: MonumentPhoto[];
};

export function MonumentPage({ monument, photos }: Props) {
  const theme = useTheme();
  const capturable = monument.readiness !== 'not_ready';
  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
    >
      <PhotoCarousel photos={photos} />
      <View style={styles.heading}>
        <Text style={[styles.title, { color: theme.text }]}>{monument.title}</Text>
        {describeLocation(monument).map((line) => (
          <Text key={line} style={[styles.location, { color: theme.secondaryText }]}>
            {line}
          </Text>
        ))}
        <View
          style={[styles.status, { backgroundColor: capturable ? theme.accent : theme.muted }]}
        >
          <Text style={[styles.statusText, { color: theme.onAccent }]}>
            {describeStatus(monument)}
          </Text>
        </View>
      </View>

      <Section title="En bref" theme={theme} />
      <View style={[styles.group, { backgroundColor: theme.surface }]}>
        {listFacts(monument).map((fact, index) => (
          <View
            key={fact.label}
            style={[
              styles.row,
              index > 0 && styles.following,
              { borderColor: theme.separator },
            ]}
          >
            <Text style={[styles.label, { color: theme.secondaryText }]}>{fact.label}</Text>
            <Text style={[styles.value, { color: theme.text }]}>{fact.value}</Text>
          </View>
        ))}
      </View>

      <Section title="Histoire" theme={theme} />
      <View style={[styles.group, { backgroundColor: theme.surface }]}>
        <Text style={[styles.note, { color: theme.secondaryText }]}>
          Fiche à enrichir : l’histoire de ce monument n’est pas encore rédigée.
        </Text>
      </View>

      <Section title="Sources" theme={theme} />
      <View style={[styles.group, { backgroundColor: theme.surface }]}>
        {listSources(monument).map((source, index) => (
          <Pressable
            key={source.url}
            style={[styles.row, index > 0 && styles.following, { borderColor: theme.separator }]}
            onPress={() => void Linking.openURL(source.url)}
            accessibilityRole="link"
          >
            <Text style={[styles.link, { color: theme.accent }]}>{source.label}</Text>
          </Pressable>
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingBottom: 32,
  },
  heading: {
    paddingHorizontal: 16,
    paddingTop: 16,
  },
  title: {
    fontSize: 26,
    fontWeight: '700',
    marginBottom: 6,
  },
  location: {
    fontSize: 15,
    lineHeight: 21,
  },
  status: {
    alignSelf: 'flex-start',
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 5,
    marginTop: 12,
  },
  statusText: {
    fontSize: 13,
    fontWeight: '600',
  },
  section: {
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'uppercase',
    paddingHorizontal: 16,
    paddingTop: 24,
    paddingBottom: 6,
  },
  group: {
    marginHorizontal: 16,
    borderRadius: 12,
    paddingHorizontal: 14,
  },
  row: {
    paddingVertical: 11,
  },
  following: {
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  label: {
    fontSize: 13,
    marginBottom: 2,
  },
  value: {
    fontSize: 16,
  },
  note: {
    fontSize: 15,
    lineHeight: 21,
    paddingVertical: 12,
  },
  link: {
    fontSize: 16,
  },
});
