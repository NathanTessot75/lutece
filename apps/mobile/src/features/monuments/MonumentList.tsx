import { Pressable, SectionList, StyleSheet, Text, View } from 'react-native';

import type { MonumentSummary } from '@/db/monuments';
import { formatArrondissement, formatCount } from '@/lib/format';
import { type Theme, useTheme } from '@/lib/theme';

import { describeMonument } from './describe';
import type { MonumentSection } from './sections';
import { useOpenMonument } from './useOpenMonument';

type RowProps = {
  monument: MonumentSummary;
  theme: Theme;
  onOpen: (id: string) => void;
};

function Row({ monument, theme, onOpen }: RowProps) {
  const dimmed = monument.readiness === 'not_ready';
  return (
    <Pressable
      style={[styles.row, { backgroundColor: theme.surface, borderColor: theme.separator }]}
      onPress={() => onOpen(monument.id)}
      accessibilityRole="button"
    >
      <Text style={[styles.title, { color: dimmed ? theme.secondaryText : theme.text }]}>
        {monument.title}
      </Text>
      <Text style={[styles.details, { color: theme.secondaryText }]}>{describeMonument(monument)}</Text>
    </Pressable>
  );
}

function Header({ section, theme }: { section: MonumentSection; theme: Theme }) {
  const name =
    section.arrondissement === null
      ? 'Sans arrondissement'
      : formatArrondissement(section.arrondissement);
  return (
    <View style={[styles.header, { backgroundColor: theme.background }]}>
      <Text style={[styles.headerText, { color: theme.secondaryText }]}>{name}</Text>
      <Text style={[styles.headerText, { color: theme.secondaryText }]}>
        {formatCount(section.data.length)}
      </Text>
    </View>
  );
}

type Props = {
  sections: MonumentSection[];
  /** A line shown above the first arrondissement. */
  caption: string;
};

export function MonumentList({ sections, caption }: Props) {
  const theme = useTheme();
  const open = useOpenMonument();
  return (
    <SectionList
      sections={sections}
      ListHeaderComponent={
        <Text style={[styles.caption, { color: theme.secondaryText }]}>{caption}</Text>
      }
      keyExtractor={(monument) => monument.id}
      renderItem={({ item }) => <Row monument={item} theme={theme} onOpen={open} />}
      renderSectionHeader={({ section }) => <Header section={section} theme={theme} />}
      contentInsetAdjustmentBehavior="automatic"
      // A pinned header would slide under the translucent navigation bar.
      stickySectionHeadersEnabled={false}
      style={{ backgroundColor: theme.background }}
    />
  );
}

const styles = StyleSheet.create({
  caption: {
    fontSize: 15,
    paddingHorizontal: 16,
    paddingTop: 4,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 18,
    paddingBottom: 6,
  },
  headerText: {
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'uppercase',
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
