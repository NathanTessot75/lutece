import { Pressable, SectionList, StyleSheet, Text, View } from 'react-native';

import { useOpenMonument } from '@/features/monuments/useOpenMonument';
import { formatDistance, formatHeading } from '@/lib/format';
import type { CompassReading, Position } from '@/lib/location';
import { type Theme, useTheme } from '@/lib/theme';

import type { Candidate } from './candidates';
import { describeCandidate } from './describe';
import type { AimTarget } from './useAim';

const COMPASS_LEVELS: Record<number, string> = {
  3: 'précise',
  2: 'moyenne',
  1: 'faible',
  0: 'à recalibrer : fais des 8 avec le téléphone',
};

function Reading({ label, value, theme }: { label: string; value: string; theme: Theme }) {
  return (
    <View style={styles.reading}>
      <Text style={[styles.readingLabel, { color: theme.secondaryText }]}>{label}</Text>
      <Text style={[styles.readingValue, { color: theme.text }]}>{value}</Text>
    </View>
  );
}

type RowProps = {
  candidate: Candidate<AimTarget>;
  captured: boolean;
  theme: Theme;
  onOpen: (id: string) => void;
};

function Row({ candidate, captured, theme, onOpen }: RowProps) {
  const bright = candidate.inSight && !captured;
  const details = describeCandidate(candidate);
  return (
    <Pressable
      style={[styles.row, { backgroundColor: theme.surface, borderColor: theme.separator }]}
      onPress={() => onOpen(candidate.target.id)}
      accessibilityRole="button"
    >
      <Text style={[styles.title, { color: bright ? theme.text : theme.secondaryText }]}>
        {candidate.target.monument.title}
      </Text>
      <Text style={[styles.details, { color: theme.secondaryText }]}>
        {captured ? `${details} · déjà capturé` : details}
      </Text>
    </Pressable>
  );
}

type Props = {
  position: Position | null;
  compass: CompassReading | null;
  candidates: Candidate<AimTarget>[];
  captured: ReadonlySet<string>;
};

/** What the phone measures, and the monuments within reach: aimed at, then around. */
export function CandidateList({ position, compass, candidates, captured }: Props) {
  const theme = useTheme();
  const open = useOpenMonument();
  const sections = [
    {
      title: 'Dans le viseur',
      empty: 'Aucun monument devant toi.',
      data: candidates.filter((candidate) => candidate.inSight),
    },
    {
      title: 'Autour de toi, hors du viseur',
      empty: 'Rien d’autre à portée.',
      data: candidates.filter((candidate) => !candidate.inSight),
    },
  ];
  return (
    <SectionList
      sections={sections}
      keyExtractor={(candidate) => candidate.target.id}
      stickySectionHeadersEnabled={false}
      contentContainerStyle={styles.content}
      ListHeaderComponent={
        <View style={[styles.readings, { backgroundColor: theme.surface }]}>
          <Reading
            label="Position"
            value={position ? `à ${formatDistance(position.accuracyM)} près` : 'recherche…'}
            theme={theme}
          />
          <Reading
            label="Cap"
            value={compass ? formatHeading(compass.headingDeg) : '—'}
            theme={theme}
          />
          <Reading
            label="Boussole"
            value={compass ? (COMPASS_LEVELS[compass.level] ?? 'inconnue') : 'indisponible'}
            theme={theme}
          />
        </View>
      }
      renderSectionHeader={({ section }) => (
        <View style={styles.header}>
          <Text style={[styles.headerText, { color: theme.secondaryText }]}>{section.title}</Text>
          {section.data.length === 0 && (
            <Text style={[styles.empty, { color: theme.secondaryText }]}>{section.empty}</Text>
          )}
        </View>
      )}
      renderItem={({ item }) => (
        <Row
          candidate={item}
          captured={captured.has(item.target.id)}
          theme={theme}
          onOpen={open}
        />
      )}
    />
  );
}

const styles = StyleSheet.create({
  content: {
    paddingBottom: 32,
  },
  readings: {
    marginHorizontal: 16,
    marginTop: 10,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 4,
  },
  reading: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 16,
    paddingVertical: 8,
  },
  readingLabel: {
    fontSize: 15,
  },
  readingValue: {
    flexShrink: 1,
    fontSize: 15,
    fontWeight: '600',
    textAlign: 'right',
  },
  header: {
    paddingHorizontal: 16,
    paddingTop: 22,
    paddingBottom: 6,
  },
  headerText: {
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'uppercase',
  },
  empty: {
    fontSize: 15,
    paddingTop: 8,
  },
  row: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  title: {
    fontSize: 16,
  },
  details: {
    fontSize: 13,
    marginTop: 2,
  },
});
