import { Pressable, SectionList, StyleSheet, Text, View } from 'react-native';

import { useOpenMonument } from '@/features/monuments/useOpenMonument';
import { formatDistance, formatHeading } from '@/lib/format';
import { useLocationAccess } from '@/lib/location';
import { type Theme, useTheme } from '@/lib/theme';

import type { Candidate } from './candidates';
import { type AimTarget, useAim } from './useAim';

// Under this many degrees aside, a monument is straight ahead.
const AHEAD_DEG = 5;

const COMPASS_LEVELS: Record<number, string> = {
  3: 'précise',
  2: 'moyenne',
  1: 'faible',
  0: 'à recalibrer : fais des 8 avec le téléphone',
};

function describeCandidate({ distanceM, offsetDeg }: Candidate): string {
  if (distanceM === 0) {
    return 'Tu es dedans';
  }
  const distance = formatDistance(distanceM);
  if (offsetDeg === null) {
    return distance;
  }
  const aside = Math.round(Math.abs(offsetDeg));
  if (aside < AHEAD_DEG) {
    return `${distance} · en face`;
  }
  return `${distance} · ${aside}° à ${offsetDeg < 0 ? 'gauche' : 'droite'}`;
}

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
  theme: Theme;
  onOpen: (id: string) => void;
};

function Row({ candidate, theme, onOpen }: RowProps) {
  return (
    <Pressable
      style={[styles.row, { backgroundColor: theme.surface, borderColor: theme.separator }]}
      onPress={() => onOpen(candidate.target.id)}
      accessibilityRole="button"
    >
      <Text
        style={[styles.title, { color: candidate.inSight ? theme.text : theme.secondaryText }]}
      >
        {candidate.target.monument.title}
      </Text>
      <Text style={[styles.details, { color: theme.secondaryText }]}>
        {describeCandidate(candidate)}
      </Text>
    </Pressable>
  );
}

/** What the phone points at, live: the first step of a capture. */
export function Aim() {
  const theme = useTheme();
  const location = useLocationAccess();
  const open = useOpenMonument();
  const { position, compass, candidates } = useAim(location.granted);

  if (!location.granted) {
    return (
      <View style={[styles.message, { backgroundColor: theme.background }]}>
        <Text style={[styles.messageText, { color: theme.secondaryText }]}>
          Pour viser un monument, Lutèce a besoin de ta position.
        </Text>
        <Pressable
          style={[styles.button, { backgroundColor: theme.accent }]}
          onPress={location.ask}
          accessibilityRole="button"
        >
          <Text style={[styles.buttonLabel, { color: theme.onAccent }]}>Activer ma position</Text>
        </Pressable>
      </View>
    );
  }

  const inSight = candidates.filter((candidate) => candidate.inSight);
  const around = candidates.filter((candidate) => !candidate.inSight);
  const sections = [
    { title: 'Dans le viseur', empty: 'Aucun monument devant toi.', data: inSight },
    { title: 'Autour de toi, hors du viseur', empty: 'Rien d’autre à portée.', data: around },
  ];
  return (
    <SectionList
      sections={sections}
      keyExtractor={(candidate) => candidate.target.id}
      contentInsetAdjustmentBehavior="automatic"
      stickySectionHeadersEnabled={false}
      style={{ backgroundColor: theme.background }}
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
      renderItem={({ item }) => <Row candidate={item} theme={theme} onOpen={open} />}
    />
  );
}

const styles = StyleSheet.create({
  message: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
    padding: 32,
  },
  messageText: {
    fontSize: 16,
    textAlign: 'center',
  },
  button: {
    borderRadius: 22,
    paddingHorizontal: 18,
    paddingVertical: 11,
  },
  buttonLabel: {
    fontSize: 16,
    fontWeight: '600',
  },
  readings: {
    marginHorizontal: 16,
    marginTop: 8,
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
