import { type Href, useRouter } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { type SFSymbol, SymbolView } from 'expo-symbols';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { countMonuments } from '@/db/monuments';
import { useBadgeBook } from '@/features/badges/useBadgeBook';
import { useCaptures } from '@/features/collection/CapturesProvider';
import { totalPoints } from '@/features/game/rarity';
import { useGroups } from '@/features/progress/useGroups';
import { formatCount } from '@/lib/format';
import { useTheme } from '@/lib/theme';
import { Text, fonts } from '@/lib/typography';

type Figure = {
  icon: SFSymbol;
  value: number;
  /** What it is out of, if anything. */
  outOf?: number;
  label: string;
  href?: Href;
};

function Tile({ figure }: { figure: Figure }) {
  const theme = useTheme();
  const router = useRouter();
  const { href } = figure;
  return (
    <Pressable
      style={({ pressed }) => [
        styles.tile,
        { backgroundColor: theme.surface },
        pressed && href !== undefined && styles.pressed,
      ]}
      onPress={href === undefined ? undefined : () => router.navigate(href)}
      disabled={href === undefined}
      accessibilityRole={href === undefined ? 'text' : 'button'}
      accessibilityLabel={`${figure.label} : ${formatCount(figure.value)}${
        figure.outOf === undefined ? '' : ` sur ${formatCount(figure.outOf)}`
      }`}
    >
      <SymbolView name={figure.icon} size={18} tintColor={theme.accent} type="monochrome" />
      <Text style={[styles.value, { color: theme.text }]}>
        {formatCount(figure.value)}
        {figure.outOf !== undefined && (
          <Text style={[styles.outOf, { color: theme.secondaryText }]}>
            {' '}
            / {formatCount(figure.outOf)}
          </Text>
        )}
      </Text>
      <Text style={[styles.label, { color: theme.secondaryText }]}>{figure.label}</Text>
    </Pressable>
  );
}

/** What the player has done, in four figures that lead to the details. */
export function PlayerFigures() {
  const db = useSQLiteContext();
  const { captures, byMonument } = useCaptures();
  const groups = useGroups();
  const badges = useBadgeBook();
  const [places, setPlaces] = useState<number | null>(null);

  useEffect(() => {
    void countMonuments(db).then(setPlaces);
  }, [db]);

  const arrondissements = groups?.arrondissements ?? [];
  const visited = arrondissements.filter((group) => group.ids.some((id) => byMonument.has(id)));
  const figures: Figure[] = [
    { icon: 'star.fill', value: totalPoints(captures), label: 'Points' },
    {
      icon: 'building.columns.fill',
      value: captures.length,
      outOf: places ?? undefined,
      label: captures.length > 1 ? 'Lieux capturés' : 'Lieu capturé',
      href: '/collection',
    },
    {
      icon: 'map.fill',
      value: visited.length,
      outOf: arrondissements.length,
      label: visited.length > 1 ? 'Arrondissements' : 'Arrondissement',
      href: '/progress',
    },
    {
      icon: 'rosette',
      value: badges?.filter((badge) => badge.wonAt !== null).length ?? 0,
      outOf: badges?.length,
      label: 'Badges',
      href: '/badges',
    },
  ];
  return (
    <View style={styles.grid}>
      {figures.map((figure) => (
        <Tile key={figure.label} figure={figure} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginHorizontal: 16,
  },
  tile: {
    flexBasis: '47%',
    flexGrow: 1,
    borderRadius: 16,
    padding: 14,
    gap: 4,
  },
  pressed: {
    opacity: 0.7,
  },
  value: {
    fontFamily: fonts.title,
    fontSize: 26,
    lineHeight: 32,
    fontVariant: ['lining-nums'],
    marginTop: 4,
  },
  outOf: {
    fontFamily: fonts.regular,
    fontSize: 15,
  },
  label: {
    fontSize: 13,
  },
});
