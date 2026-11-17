import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';
import { Linking, Pressable, SectionList, StyleSheet, View } from 'react-native';

import { type PhotoCredit, listPhotoCredits } from '@/db/monuments';
import { formatCount } from '@/lib/format';
import { useTheme } from '@/lib/theme';
import { Text } from '@/lib/typography';

type Place = { title: string; data: PhotoCredit[] };

/** The photos of the places, gathered by place in alphabetical order. */
function byPlace(credits: readonly PhotoCredit[]): Place[] {
  const places = new Map<string, Place>();
  for (const credit of credits) {
    const place = places.get(credit.monumentId) ?? { title: credit.title, data: [] };
    place.data.push(credit);
    places.set(credit.monumentId, place);
  }
  return [...places.values()].sort((a, b) => a.title.localeCompare(b.title, 'fr'));
}

/** Who took each photo of Wikimedia Commons that Lutèce uses, and under which licence. */
export function PhotoCredits() {
  const theme = useTheme();
  const db = useSQLiteContext();
  const [places, setPlaces] = useState<Place[] | null>(null);
  const [count, setCount] = useState(0);

  useEffect(() => {
    void listPhotoCredits(db).then((credits) => {
      setCount(credits.length);
      setPlaces(byPlace(credits));
    });
  }, [db]);

  return (
    <SectionList
      style={{ backgroundColor: theme.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
      sections={places ?? []}
      keyExtractor={(credit) => `${credit.monumentId}-${credit.rank}`}
      stickySectionHeadersEnabled={false}
      ListHeaderComponent={
        <Text style={[styles.lead, { color: theme.text }]}>
          {places === null
            ? ' '
            : `${formatCount(count)} photos de Wikimedia Commons, lieu par lieu. Touchez-en une pour voir sa page, avec sa licence complète.`}
        </Text>
      }
      renderSectionHeader={({ section }) => (
        <Text style={[styles.place, { color: theme.secondaryText }]}>{section.title}</Text>
      )}
      renderItem={({ item, index, section }) => (
        <Pressable
          style={({ pressed }) => [
            styles.photo,
            { backgroundColor: theme.surface, borderColor: theme.separator },
            index === 0 && styles.first,
            index > 0 && styles.following,
            index === section.data.length - 1 && styles.last,
            pressed && styles.pressed,
          ]}
          onPress={() => void Linking.openURL(item.pageUrl)}
          accessibilityRole="link"
        >
          <View style={styles.photoText}>
            <Text style={[styles.author, { color: theme.text }]} numberOfLines={2}>
              {item.author ?? 'Auteur inconnu'}
            </Text>
            <Text style={[styles.licence, { color: theme.secondaryText }]}>
              {item.licence ?? 'Licence sur Commons'}
            </Text>
          </View>
        </Pressable>
      )}
    />
  );
}

const styles = StyleSheet.create({
  content: {
    paddingBottom: 40,
  },
  lead: {
    fontSize: 15,
    lineHeight: 21,
    padding: 16,
    paddingBottom: 0,
  },
  place: {
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'uppercase',
    paddingHorizontal: 32,
    paddingTop: 20,
    paddingBottom: 6,
  },
  photo: {
    marginHorizontal: 16,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  first: {
    borderTopLeftRadius: 12,
    borderTopRightRadius: 12,
  },
  following: {
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  last: {
    borderBottomLeftRadius: 12,
    borderBottomRightRadius: 12,
  },
  pressed: {
    opacity: 0.7,
  },
  photoText: {
    gap: 1,
  },
  author: {
    fontSize: 15,
  },
  licence: {
    fontSize: 13,
  },
});
