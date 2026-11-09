import { useRouter } from 'expo-router';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import type { Capture } from '@/db/captures';
import type { MonumentDetails, MonumentPhoto } from '@/db/monuments';
import { photoUri } from '@/features/capture/photos';
import { useCaptures } from '@/features/collection/CapturesProvider';
import { advancesOf, formatProgress, isComplete } from '@/features/game/progress';
import { formatPoints, pointsFor, tierLabel } from '@/features/game/rarity';
import { capitalize, formatArrondissement, formatCentury, formatDate } from '@/lib/format';
import { type Theme, useTheme } from '@/lib/theme';

import { useGroups } from '@/features/progress/useGroups';

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
    value: monument.protection
      ? `${capitalize(monument.protection)} au titre des monuments historiques`
      : 'Aucune : ce lieu n’est pas un monument historique',
  });
  return facts;
}

function listSources(monument: MonumentDetails): Source[] {
  const sources: Source[] = [];
  if (monument.wikipedia) {
    const page = encodeURIComponent(monument.wikipedia.replaceAll(' ', '_'));
    sources.push({ label: 'Wikipédia', url: `https://fr.wikipedia.org/wiki/${page}` });
  }
  if (monument.merimeeId) {
    sources.push({
      label: 'Notice Mérimée (ministère de la Culture)',
      url: `https://pop.culture.gouv.fr/notice/merimee/${monument.merimeeId}`,
    });
  }
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

type Status = { text: string; background: string; color: string };

/** Whether the monument is captured, can be, or cannot and why. */
function describeStatus(monument: MonumentDetails, capture: Capture | null, theme: Theme): Status {
  if (capture !== null) {
    return {
      text: `Capturé le ${formatDate(capture.capturedAt)}`,
      background: theme.accent,
      color: theme.onAccent,
    };
  }
  if (monument.readiness !== 'not_ready') {
    return { text: 'À capturer', background: theme.pending, color: theme.background };
  }
  return {
    text:
      monument.visibility === 'non_visible'
        ? 'Consultation seule : sous terre'
        : 'Consultation seule : emplacement à préciser',
    background: theme.muted,
    color: theme.onAccent,
  };
}

/** What a player should know before aiming at a monument, if anything. */
function describeCaveat(monument: MonumentDetails): string | null {
  if (monument.readiness !== 'not_ready' && monument.visibility === 'non_visible') {
    return 'Ce qui est protégé ici est à l’intérieur ou sur cour : de la rue, on voit le bâtiment qui l’abrite.';
  }
  return null;
}

/** Where the story comes from, and whether a person has read it. */
function describeCredit(monument: MonumentDetails): string {
  const fromWikipedia = monument.storySources.some((source) => source.licence.startsWith('CC BY-SA'));
  const parts = ['Texte rédigé avec l’aide d’une IA à partir des sources ci-dessous'];
  if (fromWikipedia) {
    parts.push('et diffusé sous la même licence CC BY-SA 4.0');
  }
  const credit = `${parts.join(', ')}.`;
  return monument.storyReviewed ? credit : `${credit} Pas encore relu.`;
}

function Section({ title, theme }: { title: string; theme: Theme }) {
  return <Text style={[styles.section, { color: theme.secondaryText }]}>{title}</Text>;
}

type Props = {
  monument: MonumentDetails;
  photos: MonumentPhoto[];
  /** The capture of the monument by the player, if any. */
  capture: Capture | null;
};

export function MonumentPage({ monument, photos, capture }: Props) {
  const theme = useTheme();
  const status = describeStatus(monument, capture, theme);
  const caveat = describeCaveat(monument);
  const tier = monument.rarityTier;
  const router = useRouter();
  const groups = useGroups();
  const { byMonument } = useCaptures();
  const advances = groups === null ? [] : advancesOf(monument, groups, byMonument);
  const own = capture?.photoFile
    ? { uri: photoUri(capture.photoFile), caption: `Ta photo du ${formatDate(capture.capturedAt)}` }
    : null;
  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
    >
      <PhotoCarousel photos={photos} own={own} />
      <View style={styles.heading}>
        <Text style={[styles.title, { color: theme.text }]}>{monument.title}</Text>
        {describeLocation(monument).map((line) => (
          <Text key={line} style={[styles.location, { color: theme.secondaryText }]}>
            {line}
          </Text>
        ))}
        <View style={styles.badges}>
          <View style={[styles.status, { backgroundColor: status.background }]}>
            <Text style={[styles.statusText, { color: status.color }]}>{status.text}</Text>
          </View>
          {tier !== null && (
            <View style={[styles.status, styles.tier, { borderColor: theme.rarity[tier] }]}>
              <Text style={[styles.statusText, { color: theme.rarity[tier] }]}>
                {tierLabel(tier)} · {formatPoints(capture?.points ?? pointsFor(tier))}
              </Text>
            </View>
          )}
        </View>
        {caveat !== null && (
          <Text style={[styles.caveat, { color: theme.secondaryText }]}>{caveat}</Text>
        )}
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

      {advances.length > 0 && (
        <>
          <Section title="Progression" theme={theme} />
          <View style={[styles.group, { backgroundColor: theme.surface }]}>
            {advances.map((advance, index) => (
              <Pressable
                key={`${advance.kind}-${advance.key}`}
                style={[
                  styles.row,
                  styles.advance,
                  index > 0 && styles.following,
                  { borderColor: theme.separator },
                ]}
                onPress={() =>
                  advance.kind === 'series'
                    ? router.push({ pathname: '/series/[slug]', params: { slug: advance.key } })
                    : router.push({
                        pathname: '/arrondissement/[number]',
                        params: { number: advance.key },
                      })
                }
                accessibilityRole="button"
              >
                <Text style={[styles.link, styles.advanceLabel, { color: theme.accent }]}>
                  {advance.label}
                </Text>
                <Text style={[styles.value, { color: theme.secondaryText }]}>
                  {isComplete(advance.progress) ? '✓ ' : ''}
                  {formatProgress(advance.progress)}
                </Text>
              </Pressable>
            ))}
          </View>
        </>
      )}

      <Section title="Histoire" theme={theme} />
      {monument.story === null ? (
        <View style={[styles.group, { backgroundColor: theme.surface }]}>
          <Text style={[styles.note, { color: theme.secondaryText }]}>
            Fiche à enrichir : l’histoire de ce lieu n’est pas encore rédigée.
          </Text>
        </View>
      ) : (
        <View style={[styles.group, styles.story, { backgroundColor: theme.surface }]}>
          {monument.story.split(/\n\s*\n/).map((paragraph) => (
            <Text key={paragraph} style={[styles.paragraph, { color: theme.text }]}>
              {paragraph}
            </Text>
          ))}
          {monument.didYouKnow !== null && (
            <View style={[styles.didYouKnow, { borderColor: theme.accent }]}>
              <Text style={[styles.didYouKnowTitle, { color: theme.accent }]}>Le saviez-vous ?</Text>
              <Text style={[styles.paragraph, { color: theme.text }]}>{monument.didYouKnow}</Text>
            </View>
          )}
          <Text style={[styles.credit, { color: theme.secondaryText }]}>
            {describeCredit(monument)}
          </Text>
          {monument.storySources.map((source) => (
            <Pressable
              key={source.url}
              onPress={() => void Linking.openURL(source.url)}
              accessibilityRole="link"
            >
              <Text style={[styles.credit, { color: theme.accent }]}>
                {source.label} ({source.licence})
              </Text>
            </Pressable>
          ))}
        </View>
      )}

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
  badges: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 12,
  },
  status: {
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  // Outlined, as tall as the status beside it.
  tier: {
    borderWidth: 1.5,
    paddingHorizontal: 8.5,
    paddingVertical: 3.5,
  },
  statusText: {
    fontSize: 13,
    fontWeight: '600',
  },
  caveat: {
    fontSize: 14,
    lineHeight: 20,
    marginTop: 10,
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
  story: {
    paddingVertical: 12,
    gap: 12,
  },
  paragraph: {
    fontSize: 16,
    lineHeight: 23,
  },
  didYouKnow: {
    borderLeftWidth: 3,
    paddingLeft: 12,
    gap: 4,
  },
  didYouKnowTitle: {
    fontSize: 14,
    fontWeight: '700',
  },
  credit: {
    fontSize: 13,
    lineHeight: 18,
  },
  note: {
    fontSize: 15,
    lineHeight: 21,
    paddingVertical: 12,
  },
  link: {
    fontSize: 16,
  },
  advance: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 12,
  },
  advanceLabel: {
    flex: 1,
  },
});
