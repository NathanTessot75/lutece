import { Pressable, StyleSheet, View } from 'react-native';

import { type Progress, formatProgress, isComplete } from '@/features/game/progress';
import { useTheme } from '@/lib/theme';
import { Text } from '@/lib/typography';

type Props = {
  label: string;
  progress: Progress;
  /** Whether a line separates it from the row above. */
  following: boolean;
  onPress: () => void;
};

/** A series or an arrondissement: its name, how far the player is, and a bar. */
export function GroupRow({ label, progress, following, onPress }: Props) {
  const theme = useTheme();
  const complete = isComplete(progress);
  const share = progress.total === 0 ? 0 : progress.captured / progress.total;
  return (
    <Pressable
      style={[styles.row, following && styles.following, { borderColor: theme.separator }]}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${label}, ${progress.captured} sur ${progress.total}`}
    >
      <View style={styles.line}>
        <Text style={[styles.label, { color: theme.text }]} numberOfLines={1}>
          {label}
        </Text>
        <Text style={[styles.count, { color: complete ? theme.accent : theme.secondaryText }]}>
          {complete ? '✓ ' : ''}
          {formatProgress(progress)}
        </Text>
      </View>
      <View style={[styles.track, { backgroundColor: theme.separator }]}>
        <View
          style={[
            styles.fill,
            { width: `${share * 100}%`, backgroundColor: complete ? theme.gold : theme.pending },
          ]}
        />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { paddingVertical: 11, gap: 7 },
  following: { borderTopWidth: StyleSheet.hairlineWidth },
  line: { flexDirection: 'row', alignItems: 'baseline', gap: 12 },
  label: { flex: 1, fontSize: 16 },
  count: { fontSize: 15, fontWeight: '600', fontVariant: ['tabular-nums'] },
  track: { height: 5, borderRadius: 3, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 3 },
});
