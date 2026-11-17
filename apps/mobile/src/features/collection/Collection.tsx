import { useSQLiteContext } from 'expo-sqlite';
import { SymbolView } from 'expo-symbols';
import { useEffect, useState } from 'react';
import {
  Image,
  Pressable,
  SectionList,
  StyleSheet,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';

import type { Capture } from '@/db/captures';
import { type MonumentSummary, type RarityTier, listMonuments } from '@/db/monuments';
import { photoUri } from '@/features/capture/photos';
import { formatPoints, tierLabel, totalPoints } from '@/features/game/rarity';
import { useOpenMonument } from '@/features/monuments/useOpenMonument';
import { formatArrondissement, formatCount } from '@/lib/format';
import { useTabBarInsets } from '@/lib/tabBar';
import { type Theme, useTheme } from '@/lib/theme';
import { Text, fonts } from '@/lib/typography';

import { useCaptures } from './CapturesProvider';
import {
  type Entry,
  type Filter,
  chapters,
  countByTier,
  formatNumber,
  numberPlaces,
  rows,
} from './catalogue';

const COLUMNS = 3;
const MARGIN = 16;
const GAP = 10;
const TIERS: readonly RarityTier[] = ['commun', 'peu_commun', 'rare', 'légendaire'];
const FILTERS: readonly { filter: Filter; label: string }[] = [
  { filter: 'all', label: 'Tous' },
  { filter: 'captured', label: 'Capturés' },
  { filter: 'toCapture', label: 'À capturer' },
];

type CardProps = {
  entry: Entry;
  capture: Capture | undefined;
  size: number;
  theme: Theme;
  onOpen: (id: string) => void;
};

/** A place of the catalogue: its photo once captured, its silhouette before. */
function Card({ entry, capture, size, theme, onOpen }: CardProps) {
  const { monument, number } = entry;
  const tier = monument.rarityTier;
  const captured = capture !== undefined;
  return (
    <Pressable
      style={({ pressed }) => [
        styles.card,
        {
          width: size,
          backgroundColor: theme.surface,
          borderColor: captured ? theme.captured : 'transparent',
        },
        pressed && styles.pressed,
      ]}
      onPress={() => onOpen(monument.id)}
      accessibilityRole="button"
      accessibilityLabel={[
        formatNumber(number),
        monument.title,
        captured ? 'capturé' : 'à capturer',
        tier && tierLabel(tier),
      ]
        .filter(Boolean)
        .join(', ')}
    >
      <View style={[styles.picture, { height: size - 4, backgroundColor: theme.background }]}>
        {capture?.photoFile ? (
          <Image
            source={{ uri: photoUri(capture.photoFile) }}
            style={StyleSheet.absoluteFill}
            resizeMode="cover"
            accessibilityIgnoresInvertColors
          />
        ) : (
          <SymbolView
            name="building.columns.fill"
            size={size * 0.38}
            tintColor={captured ? theme.captured : theme.separator}
            type="monochrome"
          />
        )}
        {captured && (
          <View style={[styles.seal, { backgroundColor: theme.captured }]}>
            <SymbolView
              name="checkmark"
              size={10}
              tintColor={theme.onCaptured}
              weight="bold"
              type="monochrome"
            />
          </View>
        )}
      </View>
      <View style={styles.label}>
        <View style={styles.numberLine}>
          <Text style={[styles.number, { color: theme.secondaryText }]}>{formatNumber(number)}</Text>
          {tier !== null && <View style={[styles.dot, { backgroundColor: theme.rarity[tier] }]} />}
        </View>
        <Text
          style={[styles.name, { color: captured ? theme.text : theme.secondaryText }]}
          numberOfLines={2}
        >
          {monument.title}
        </Text>
      </View>
    </Pressable>
  );
}

type HeroProps = {
  monuments: readonly MonumentSummary[];
  captured: { has: (id: string) => boolean };
  points: number;
  theme: Theme;
};

/** How much of the city is captured, in all and by rarity. */
function Hero({ monuments, captured, points, theme }: HeroProps) {
  const total = monuments.length;
  const count = monuments.filter((monument) => captured.has(monument.id)).length;
  const tiers = countByTier(monuments, captured);
  return (
    <View style={[styles.hero, { backgroundColor: theme.surface }]}>
      <View style={styles.heroLine}>
        <Text style={[styles.heroCount, { color: theme.text }]}>{formatCount(count)}</Text>
        <Text style={[styles.heroTotal, { color: theme.secondaryText }]}>
          / {formatCount(total)} {count > 1 ? 'lieux capturés' : 'lieu capturé'}
        </Text>
        <Text style={[styles.heroPoints, { color: theme.rarity.légendaire }]}>
          {formatPoints(points)}
        </Text>
      </View>
      <View style={[styles.track, { backgroundColor: theme.separator }]}>
        <View
          style={[
            styles.fill,
            {
              width: `${total === 0 ? 0 : (count / total) * 100}%`,
              backgroundColor: theme.captured,
            },
          ]}
        />
      </View>
      <View style={styles.tiers}>
        {TIERS.map((tier) => (
          <View
            key={tier}
            style={styles.tier}
            accessible
            accessibilityLabel={`${tierLabel(tier)} : ${tiers[tier].captured} sur ${tiers[tier].total}`}
          >
            <View style={[styles.dot, { backgroundColor: theme.rarity[tier] }]} />
            <Text style={[styles.tierCount, { color: theme.secondaryText }]}>
              {tiers[tier].captured}/{tiers[tier].total}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

type FiltersProps = {
  filter: Filter;
  onFilter: (filter: Filter) => void;
  search: string | null;
  onSearch: (search: string | null) => void;
  theme: Theme;
};

/** All the places, those captured or those to capture; and a search by name or number. */
function Filters({ filter, onFilter, search, onSearch, theme }: FiltersProps) {
  return (
    <View style={styles.filters}>
      <View style={styles.chips}>
        {FILTERS.map((one) => {
          const chosen = one.filter === filter;
          return (
            <Pressable
              key={one.filter}
              style={[styles.chip, { backgroundColor: chosen ? theme.accent : theme.surface }]}
              onPress={() => onFilter(one.filter)}
              accessibilityRole="button"
              accessibilityState={{ selected: chosen }}
            >
              <Text style={[styles.chipLabel, { color: chosen ? theme.onAccent : theme.text }]}>
                {one.label}
              </Text>
            </Pressable>
          );
        })}
        <Pressable
          style={[
            styles.chip,
            styles.searchChip,
            { backgroundColor: search === null ? theme.surface : theme.accent },
          ]}
          onPress={() => onSearch(search === null ? '' : null)}
          accessibilityRole="button"
          accessibilityLabel={search === null ? 'Chercher un lieu' : 'Fermer la recherche'}
        >
          <SymbolView
            name="magnifyingglass"
            size={15}
            tintColor={search === null ? theme.text : theme.onAccent}
            weight="semibold"
            type="monochrome"
          />
        </Pressable>
      </View>
      {search !== null && (
        <View style={[styles.search, { backgroundColor: theme.surface }]}>
          <TextInput
            style={[styles.searchInput, { color: theme.text, fontFamily: fonts.regular }]}
            value={search}
            onChangeText={onSearch}
            placeholder="Nom ou numéro"
            placeholderTextColor={theme.secondaryText}
            autoFocus
            autoCorrect={false}
            clearButtonMode="while-editing"
            returnKeyType="search"
          />
        </View>
      )}
    </View>
  );
}

/** Every place of the app, numbered like a catalogue, the captured ones in colour. */
export function Collection() {
  const db = useSQLiteContext();
  const theme = useTheme();
  const tabBarInsets = useTabBarInsets();
  const open = useOpenMonument();
  const { width } = useWindowDimensions();
  const { captures, byMonument } = useCaptures();
  const [monuments, setMonuments] = useState<MonumentSummary[] | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  // Null while the search is closed.
  const [search, setSearch] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    void listMonuments(db).then((found) => {
      if (current) {
        setMonuments(found);
      }
    });
    return () => {
      current = false;
    };
  }, [db]);

  const size = (width - 2 * MARGIN - (COLUMNS - 1) * GAP) / COLUMNS;
  const kept = chapters(numberPlaces(monuments ?? []), filter, search ?? '', byMonument);
  const sections = kept.map((chapter) => ({ chapter, data: rows(chapter.entries, COLUMNS) }));
  const empty =
    filter === 'captured' && !search
      ? 'Votre collection est vide. Approchez-vous d’un monument et capturez-le depuis l’onglet Photo.'
      : 'Aucun lieu ne correspond.';
  return (
    <SectionList
      sections={sections}
      keyExtractor={(row) => row[0].monument.id}
      contentInsetAdjustmentBehavior="automatic"
      {...tabBarInsets}
      keyboardDismissMode="on-drag"
      keyboardShouldPersistTaps="handled"
      // A pinned header would slide under the translucent navigation bar.
      stickySectionHeadersEnabled={false}
      style={{ backgroundColor: theme.background }}
      ListHeaderComponent={
        monuments === null ? null : (
          <>
            <Hero
              monuments={monuments}
              captured={byMonument}
              points={totalPoints(captures)}
              theme={theme}
            />
            <Filters
              filter={filter}
              onFilter={setFilter}
              search={search}
              onSearch={setSearch}
              theme={theme}
            />
          </>
        )
      }
      ListEmptyComponent={
        monuments === null ? null : (
          <Text style={[styles.empty, { color: theme.secondaryText }]}>{empty}</Text>
        )
      }
      renderSectionHeader={({ section: { chapter } }) => (
        <View style={styles.chapter}>
          <Text style={[styles.chapterTitle, { color: theme.text }]}>
            {chapter.arrondissement === null
              ? 'Hors des arrondissements'
              : formatArrondissement(chapter.arrondissement)}
          </Text>
          <Text style={[styles.chapterCount, { color: theme.secondaryText }]}>
            {chapter.captured} / {chapter.total}
          </Text>
        </View>
      )}
      renderItem={({ item }) => (
        <View style={styles.row}>
          {item.map((entry) => (
            <Card
              key={entry.monument.id}
              entry={entry}
              capture={byMonument.get(entry.monument.id)}
              size={size}
              theme={theme}
              onOpen={open}
            />
          ))}
        </View>
      )}
    />
  );
}

const styles = StyleSheet.create({
  hero: {
    marginHorizontal: MARGIN,
    marginTop: 4,
    borderRadius: 20,
    padding: 16,
    gap: 10,
  },
  heroLine: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 6,
  },
  // Playfair draws old-style figures: « 1er » would read « ıer ».
  heroCount: {
    fontFamily: fonts.title,
    fontSize: 34,
    lineHeight: 40,
    fontVariant: ['lining-nums'],
  },
  heroTotal: {
    flex: 1,
    fontSize: 15,
  },
  heroPoints: {
    fontSize: 15,
    fontWeight: '700',
  },
  track: {
    height: 7,
    borderRadius: 4,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: 4,
  },
  tiers: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  tier: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  tierCount: {
    fontSize: 13,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
  filters: {
    marginHorizontal: MARGIN,
    marginTop: 14,
    gap: 10,
  },
  chips: {
    flexDirection: 'row',
    gap: 8,
  },
  chip: {
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  searchChip: {
    marginLeft: 'auto',
    paddingHorizontal: 12,
    justifyContent: 'center',
  },
  chipLabel: {
    fontSize: 14,
    fontWeight: '600',
  },
  search: {
    borderRadius: 14,
    paddingHorizontal: 14,
  },
  searchInput: {
    fontSize: 16,
    paddingVertical: 11,
  },
  chapter: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    marginHorizontal: MARGIN,
    marginTop: 22,
    marginBottom: 10,
  },
  chapterTitle: {
    fontFamily: fonts.title,
    fontSize: 21,
    fontVariant: ['lining-nums'],
  },
  chapterCount: {
    fontSize: 14,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
  row: {
    flexDirection: 'row',
    gap: GAP,
    marginHorizontal: MARGIN,
    marginBottom: GAP,
  },
  card: {
    borderRadius: 16,
    borderWidth: 2,
    overflow: 'hidden',
  },
  pressed: {
    opacity: 0.75,
  },
  picture: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  seal: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 20,
    height: 20,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: {
    paddingHorizontal: 8,
    paddingTop: 6,
    paddingBottom: 9,
    gap: 2,
  },
  numberLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  number: {
    fontSize: 11,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 4,
  },
  name: {
    fontSize: 13,
    lineHeight: 16,
    fontWeight: '600',
    minHeight: 32,
  },
  empty: {
    fontSize: 16,
    lineHeight: 23,
    marginHorizontal: MARGIN,
    marginTop: 24,
  },
});
