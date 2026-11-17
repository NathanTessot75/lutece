import { SymbolView } from 'expo-symbols';
import type { ReactNode } from 'react';
import { Linking, Pressable, StyleSheet, View } from 'react-native';

import { useTheme } from '@/lib/theme';
import { Text } from '@/lib/typography';

/** The opening sentence of a page. */
export function Lead({ children }: { children: ReactNode }) {
  const theme = useTheme();
  return <Text style={[styles.lead, { color: theme.text }]}>{children}</Text>;
}

/** A part of a page: a title, then what it says. */
export function Part({ title, children }: { title: string; children: ReactNode }) {
  const theme = useTheme();
  return (
    <View style={styles.part}>
      <Text style={[styles.title, { color: theme.text }]}>{title}</Text>
      {children}
    </View>
  );
}

export function Paragraph({ children }: { children: ReactNode }) {
  const theme = useTheme();
  return <Text style={[styles.paragraph, { color: theme.secondaryText }]}>{children}</Text>;
}

type Source = {
  name: string;
  /** What Lutèce takes from it. */
  what: string;
  licence?: string;
  /** Where it lives on the web; without it, the row leads to a page of the app. */
  url?: string;
};

/**
 * Where something comes from, under which licence, with a link to it; or,
 * given what to do instead, a page of the app about it.
 */
export function SourceRow({ source, onPress }: { source: Source; onPress?: () => void }) {
  const theme = useTheme();
  const { url } = source;
  return (
    <Pressable
      style={({ pressed }) => [
        styles.source,
        { backgroundColor: theme.surface },
        pressed && styles.pressed,
      ]}
      onPress={onPress ?? (url === undefined ? undefined : () => void Linking.openURL(url))}
      accessibilityRole={onPress === undefined ? 'link' : 'button'}
      accessibilityLabel={`${source.name}${source.licence ? `, ${source.licence}` : ''}. ${source.what}`}
    >
      <View style={styles.sourceText}>
        <View style={styles.sourceHead}>
          <Text style={[styles.sourceName, { color: theme.text }]}>{source.name}</Text>
          {source.licence !== undefined && (
            <Text style={[styles.licence, { color: theme.accent }]}>{source.licence}</Text>
          )}
        </View>
        <Text style={[styles.what, { color: theme.secondaryText }]}>{source.what}</Text>
      </View>
      <SymbolView
        name={onPress === undefined ? 'arrow.up.right' : 'chevron.right'}
        size={13}
        tintColor={theme.secondaryText}
        weight="semibold"
        type="monochrome"
      />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  lead: {
    fontSize: 17,
    lineHeight: 24,
  },
  part: {
    gap: 8,
    paddingTop: 12,
  },
  title: {
    fontSize: 17,
    fontWeight: '600',
  },
  paragraph: {
    fontSize: 15,
    lineHeight: 22,
  },
  source: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  pressed: {
    opacity: 0.7,
  },
  sourceText: {
    flex: 1,
    gap: 2,
  },
  sourceHead: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'baseline',
    columnGap: 8,
  },
  sourceName: {
    fontSize: 16,
    fontWeight: '600',
  },
  licence: {
    fontSize: 13,
    fontWeight: '600',
  },
  what: {
    fontSize: 14,
    lineHeight: 19,
  },
});
