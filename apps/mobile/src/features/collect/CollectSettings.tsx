import { useSQLiteContext } from 'expo-sqlite';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Switch, View } from 'react-native';

import { listMonumentsByIds } from '@/db/monuments';
import { formatCount, formatDate } from '@/lib/format';
import { useTheme } from '@/lib/theme';

import { useContribution } from '@/features/contribute/ContributeProvider';
import { Text } from '@/lib/typography';

import { useCollect } from './CollectProvider';

// How many of the latest samples the screen lists.
const LATEST = 20;

/** Turn the collect mode on or off, and see what has been collected. */
export function CollectSettings() {
  const db = useSQLiteContext();
  const theme = useTheme();
  const router = useRouter();
  const { enabled, setEnabled, samples } = useCollect();
  const contribution = useContribution();
  const [titles, setTitles] = useState<ReadonlyMap<string, string>>(new Map());

  const latest = samples.slice(0, LATEST);
  const ids = latest.flatMap((sample) => (sample.labelMonumentId ? [sample.labelMonumentId] : []));
  const key = ids.join(',');
  useEffect(() => {
    let current = true;
    void listMonumentsByIds(db, key ? key.split(',') : []).then((found) => {
      if (current) {
        setTitles(new Map(found.map((monument) => [monument.id, monument.title])));
      }
    });
    return () => {
      current = false;
    };
  }, [db, key]);

  const none = samples.filter((sample) => sample.labelMonumentId === null).length;
  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
    >
      <Pressable
        style={[styles.group, styles.switchRow, { backgroundColor: theme.surface }]}
        onPress={() => void setEnabled(!enabled)}
        accessibilityRole="switch"
        accessibilityState={{ checked: enabled }}
      >
        <Text style={[styles.title, { color: theme.text }]}>Mode collecte</Text>
        <Switch
          value={enabled}
          onValueChange={(next) => void setEnabled(next)}
          trackColor={{ true: theme.accent }}
        />
      </Pressable>
      <Text style={[styles.note, { color: theme.secondaryText }]}>
        Chaque photo prise depuis l’écran de capture devient un exemple du jeu de test : Lutèce
        garde la photo, ta position, ton cap, ce qu’elle aurait décidé et le monument que tu lui
        indiques. Rien n’est ajouté à ta collection, et rien ne quitte le téléphone, sauf si tu
        contribues tes photos.
      </Text>
      {contribution.available && (
        <Pressable
          style={[styles.group, styles.switchRow, { backgroundColor: theme.surface }]}
          onPress={() => router.push('/contribute')}
          accessibilityRole="button"
        >
          <Text style={[styles.label, { color: theme.text }]}>Contribuer mes photos</Text>
          <Text style={[styles.date, { color: theme.secondaryText }]}>
            {contribution.enabled ? 'Activé' : 'Désactivé'}
          </Text>
        </Pressable>
      )}
      <Text style={[styles.count, { color: theme.text }]}>
        {formatCount(samples.length)} {samples.length > 1 ? 'photos' : 'photo'}
        {none > 0 ? ` · ${formatCount(none)} sans monument` : ''}
      </Text>
      {latest.length > 0 && (
        <View style={[styles.group, { backgroundColor: theme.surface }]}>
          {latest.map((sample, index) => (
            <View
              key={sample.id}
              style={[
                styles.row,
                index > 0 && {
                  borderTopColor: theme.separator,
                  borderTopWidth: StyleSheet.hairlineWidth,
                },
              ]}
            >
              <Text style={[styles.label, { color: theme.text }]} numberOfLines={1}>
                {sample.labelMonumentId === null
                  ? 'Aucun monument'
                  : (titles.get(sample.labelMonumentId) ?? '…')}
              </Text>
              <Text style={[styles.date, { color: theme.secondaryText }]}>
                {formatDate(sample.takenAt)}
              </Text>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 12 },
  group: { borderRadius: 14, overflow: 'hidden' },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  title: { fontSize: 17, fontWeight: '600' },
  note: { fontSize: 14, lineHeight: 20 },
  count: { fontSize: 17, fontWeight: '600', marginTop: 8 },
  row: { paddingHorizontal: 14, paddingVertical: 10 },
  label: { fontSize: 16 },
  date: { fontSize: 13, marginTop: 2 },
});
