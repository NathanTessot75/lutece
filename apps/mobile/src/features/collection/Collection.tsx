import { useRouter } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';
import { FlatList, Image, Pressable, StyleSheet, View } from 'react-native';

import { BUNDLE_MONUMENT_COUNT } from '@/db/bundle';
import type { Capture } from '@/db/captures';
import {
  type MonumentSummary,
  countCapturable,
  listMonuments,
  listMonumentsByIds,
} from '@/db/monuments';
import { photoUri } from '@/features/capture/photos';
import { useBadgeBook } from '@/features/badges/useBadgeBook';
import { useContribution } from '@/features/contribute/ContributeProvider';
import { formatPoints, totalPoints } from '@/features/game/rarity';
import { useRanking } from '@/features/ranking/RankingProvider';
import { MonumentList } from '@/features/monuments/MonumentList';
import { type MonumentSection, groupByArrondissement } from '@/features/monuments/sections';
import { useOpenMonument } from '@/features/monuments/useOpenMonument';
import { formatCount, formatDate } from '@/lib/format';
import { type Theme, useTheme } from '@/lib/theme';
import { Text } from '@/lib/typography';

import { useCaptures } from './CapturesProvider';

type RowProps = {
  capture: Capture;
  monument: MonumentSummary;
  theme: Theme;
  onOpen: (id: string) => void;
};

function Row({ capture, monument, theme, onOpen }: RowProps) {
  return (
    <Pressable
      style={[styles.row, { backgroundColor: theme.surface, borderColor: theme.separator }]}
      onPress={() => onOpen(monument.id)}
      accessibilityRole="button"
    >
      {capture.photoFile === null ? (
        <View style={[styles.photo, { backgroundColor: theme.separator }]} />
      ) : (
        <Image
          source={{ uri: photoUri(capture.photoFile) }}
          style={[styles.photo, { backgroundColor: theme.separator }]}
          accessibilityIgnoresInvertColors
        />
      )}
      <View style={styles.text}>
        <Text style={[styles.title, { color: theme.text }]} numberOfLines={3}>
          {monument.title}
        </Text>
        <Text style={[styles.details, { color: theme.secondaryText }]}>
          Capturé le {formatDate(capture.capturedAt)}
        </Text>
      </View>
    </Pressable>
  );
}

function ContributeLink({ theme }: { theme: Theme }) {
  const router = useRouter();
  const { available, enabled } = useContribution();
  if (!available) {
    return null;
  }
  return (
    <Pressable
      style={[styles.card, styles.contribute, { backgroundColor: theme.surface }]}
      onPress={() => router.push('/contribute')}
      accessibilityRole="button"
    >
      <Text style={[styles.title, { color: theme.text }]}>Contribuer mes photos</Text>
      <Text style={[styles.details, { color: theme.secondaryText }]}>
        {enabled ? 'Activé' : 'Désactivé'}
      </Text>
    </Pressable>
  );
}

function ProgressLink({ theme }: { theme: Theme }) {
  const router = useRouter();
  return (
    <Pressable
      style={[styles.card, styles.progress, { backgroundColor: theme.surface }]}
      onPress={() => router.push('/progress')}
      accessibilityRole="button"
    >
      <Text style={[styles.title, { color: theme.text }]}>Progression</Text>
      <Text style={[styles.details, { color: theme.secondaryText }]}>Arrondissements et séries</Text>
    </Pressable>
  );
}

function BadgesLink({ theme }: { theme: Theme }) {
  const router = useRouter();
  const states = useBadgeBook();
  const won = states?.filter((state) => state.wonAt !== null).length;
  return (
    <Pressable
      style={[styles.card, styles.progress, { backgroundColor: theme.surface }]}
      onPress={() => router.push('/badges')}
      accessibilityRole="button"
    >
      <Text style={[styles.title, { color: theme.text }]}>Badges</Text>
      <Text style={[styles.details, { color: theme.secondaryText }]}>
        {states === null ? ' ' : `${won}/${states.length}`}
      </Text>
    </Pressable>
  );
}

function LeaderboardLink({ theme }: { theme: Theme }) {
  const router = useRouter();
  const { available, username } = useRanking();
  if (!available) {
    return null;
  }
  return (
    <Pressable
      style={[styles.card, styles.progress, { backgroundColor: theme.surface }]}
      onPress={() => router.push('/leaderboard')}
      accessibilityRole="button"
    >
      <Text style={[styles.title, { color: theme.text }]}>Classement</Text>
      <Text style={[styles.details, { color: theme.secondaryText }]} numberOfLines={1}>
        {username ?? 'Rejoindre'}
      </Text>
    </Pressable>
  );
}

type Shown = 'captures' | 'places';

const VIEWS: readonly { view: Shown; label: string }[] = [
  { view: 'captures', label: 'Mes captures' },
  { view: 'places', label: 'Tous les lieux' },
];

/** The two views of the collection, as tabs under the title. */
function Views({ shown, onShow, theme }: { shown: Shown; onShow: (view: Shown) => void; theme: Theme }) {
  return (
    <View style={[styles.views, { borderColor: theme.separator }]} accessibilityRole="tablist">
      {VIEWS.map(({ view, label }) => {
        const chosen = view === shown;
        return (
          <Pressable
            key={view}
            style={[styles.view, chosen && { borderColor: theme.accent }]}
            onPress={() => onShow(view)}
            accessibilityRole="tab"
            accessibilityState={{ selected: chosen }}
          >
            <Text style={[styles.viewLabel, { color: chosen ? theme.accent : theme.secondaryText }]}>
              {label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function countLine(captured: number, capturable: number, points: number): string {
  const what = captured > 1 ? 'monuments capturés' : 'monument capturé';
  return `${formatCount(captured)} ${what} sur ${formatCount(capturable)} · ${formatPoints(points)}`;
}

/** What the player has captured, the latest first. */
export function Collection() {
  const db = useSQLiteContext();
  const theme = useTheme();
  const open = useOpenMonument();
  const { captures } = useCaptures();
  const [monuments, setMonuments] = useState<ReadonlyMap<string, MonumentSummary>>(new Map());
  const [capturable, setCapturable] = useState<number | null>(null);
  const [view, setView] = useState<Shown>('captures');
  const [sections, setSections] = useState<MonumentSection[] | null>(null);

  useEffect(() => {
    let current = true;
    void countCapturable(db).then((count) => {
      if (current) {
        setCapturable(count);
      }
    });
    return () => {
      current = false;
    };
  }, [db]);

  useEffect(() => {
    let current = true;
    const ids = captures.map((capture) => capture.monumentId);
    void listMonumentsByIds(db, ids).then((found) => {
      if (current) {
        setMonuments(new Map(found.map((monument) => [monument.id, monument])));
      }
    });
    return () => {
      current = false;
    };
  }, [db, captures]);

  // Every place, by arrondissement, the first time it is asked for.
  const wantsPlaces = view === 'places';
  useEffect(() => {
    if (!wantsPlaces) {
      return;
    }
    let current = true;
    void listMonuments(db).then((found) => {
      if (current) {
        setSections(groupByArrondissement(found));
      }
    });
    return () => {
      current = false;
    };
  }, [db, wantsPlaces]);

  const tabs = <Views shown={view} onShow={setView} theme={theme} />;
  if (view === 'places') {
    return (
      <MonumentList
        header={tabs}
        sections={sections ?? []}
        caption={`${formatCount(BUNDLE_MONUMENT_COUNT)} monuments et lieux de Paris`}
      />
    );
  }

  // A capture whose monument has left the bundle is kept, but not shown.
  const shown = captures.flatMap((capture) => {
    const monument = monuments.get(capture.monumentId);
    return monument ? [{ capture, monument }] : [];
  });
  return (
    <FlatList
      data={shown}
      keyExtractor={({ capture }) => capture.monumentId}
      contentInsetAdjustmentBehavior="automatic"
      style={{ backgroundColor: theme.background }}
      ListHeaderComponent={
        <>
          {tabs}
          <Text style={[styles.caption, { color: theme.secondaryText }]}>
            {capturable === null ? ' ' : countLine(captures.length, capturable, totalPoints(captures))}
          </Text>
          <ProgressLink theme={theme} />
          <BadgesLink theme={theme} />
          <LeaderboardLink theme={theme} />
        </>
      }
      ListEmptyComponent={
        captures.length === 0 ? (
          <Text style={[styles.empty, { color: theme.secondaryText }]}>
            Ta collection est vide. Approche-toi d’un monument et capture-le depuis l’onglet Photo.
          </Text>
        ) : null
      }
      ListFooterComponent={<ContributeLink theme={theme} />}
      renderItem={({ item }) => (
        <Row capture={item.capture} monument={item.monument} theme={theme} onOpen={open} />
      )}
    />
  );
}

const styles = StyleSheet.create({
  views: {
    flexDirection: 'row',
    marginHorizontal: 16,
    marginBottom: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  view: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 2,
    borderColor: 'transparent',
    marginBottom: -StyleSheet.hairlineWidth,
  },
  viewLabel: {
    fontSize: 15,
    fontWeight: '600',
  },
  caption: {
    fontSize: 15,
    paddingHorizontal: 16,
    paddingTop: 4,
    paddingBottom: 12,
  },
  empty: {
    fontSize: 16,
    lineHeight: 23,
    paddingHorizontal: 16,
    paddingTop: 24,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  photo: {
    width: 72,
    height: 72,
    borderRadius: 10,
  },
  text: {
    flex: 1,
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
  },
  details: {
    fontSize: 13,
    marginTop: 3,
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 14,
  },
  progress: {
    marginHorizontal: 16,
    marginBottom: 16,
  },
  contribute: {
    margin: 16,
  },
});
