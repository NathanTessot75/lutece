import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { formatDistance } from '@/lib/format';
import { type Theme, useTheme } from '@/lib/theme';

import type { LabelChoice } from './sample';

export type Label = {
  /** The monument the photo shows; none for no monument of the app. */
  monumentId: string | null;
  oblique: boolean;
  hidden: boolean;
};

type Props = {
  choices: LabelChoice[];
  onLabel: (label: Label) => void;
  onCancel: () => void;
};

function where(choice: LabelChoice): string {
  const distance = formatDistance(choice.distanceM);
  if (choice.inSight) {
    return `${distance} · dans le viseur`;
  }
  return choice.inReach ? `${distance} · à portée` : distance;
}

function Toggle(props: { label: string; on: boolean; onPress: () => void; theme: Theme }) {
  const { label, on, onPress, theme } = props;
  return (
    <Pressable
      style={[
        styles.toggle,
        { borderColor: theme.accent, backgroundColor: on ? theme.accent : 'transparent' },
      ]}
      onPress={onPress}
      accessibilityRole="switch"
      accessibilityState={{ checked: on }}
    >
      <Text style={[styles.toggleLabel, { color: on ? theme.onAccent : theme.accent }]}>
        {label}
      </Text>
    </Pressable>
  );
}

/** In collect mode, the player tells what the photo shows: the label of the sample. */
export function LabelSample({ choices, onLabel, onCancel }: Props) {
  const theme = useTheme();
  const [oblique, setOblique] = useState(false);
  const [hidden, setHidden] = useState(false);
  const label = (monumentId: string | null) => onLabel({ monumentId, oblique, hidden });

  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
    >
      <Text style={[styles.question, { color: theme.text }]}>Qu’as-tu photographié ?</Text>
      <Text style={[styles.hint, { color: theme.secondaryText }]}>
        Mode collecte : choisis le monument que montre ta photo. Elle rejoint le jeu de test, pas
        ta collection.
      </Text>
      <View style={styles.toggles}>
        <Toggle label="De biais" on={oblique} onPress={() => setOblique(!oblique)} theme={theme} />
        <Toggle
          label="En partie caché"
          on={hidden}
          onPress={() => setHidden(!hidden)}
          theme={theme}
        />
      </View>
      <View style={[styles.group, { backgroundColor: theme.surface }]}>
        {choices.map((choice, index) => (
          <Pressable
            key={choice.id}
            style={[
              styles.row,
              index > 0 && { borderTopColor: theme.separator, borderTopWidth: StyleSheet.hairlineWidth },
            ]}
            onPress={() => label(choice.id)}
            accessibilityRole="button"
          >
            <Text style={[styles.title, { color: theme.text }]} numberOfLines={2}>
              {choice.title}
            </Text>
            <Text style={[styles.details, { color: theme.secondaryText }]}>{where(choice)}</Text>
          </Pressable>
        ))}
        {choices.length === 0 && (
          <Text style={[styles.empty, { color: theme.secondaryText }]}>
            Aucun monument à moins de 300 m.
          </Text>
        )}
      </View>
      <Pressable
        style={[styles.none, { backgroundColor: theme.surface }]}
        onPress={() => label(null)}
        accessibilityRole="button"
      >
        <Text style={[styles.title, { color: theme.text }]}>Aucun monument de Lutèce</Text>
        <Text style={[styles.details, { color: theme.secondaryText }]}>
          Une rue, un immeuble, un lieu qui n’est pas dans l’app
        </Text>
      </Pressable>
      <Pressable style={styles.cancel} onPress={onCancel} accessibilityRole="button">
        <Text style={[styles.cancelLabel, { color: theme.accent }]}>Ne pas garder cette photo</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 12 },
  question: { fontSize: 28, fontWeight: '700' },
  hint: { fontSize: 15, lineHeight: 21 },
  toggles: { flexDirection: 'row', gap: 8 },
  toggle: { borderWidth: 1.5, borderRadius: 16, paddingHorizontal: 12, paddingVertical: 6 },
  toggleLabel: { fontSize: 15, fontWeight: '600' },
  group: { borderRadius: 14, overflow: 'hidden' },
  row: { paddingHorizontal: 14, paddingVertical: 11 },
  title: { fontSize: 17, fontWeight: '600' },
  details: { fontSize: 14, marginTop: 2 },
  empty: { fontSize: 15, padding: 14 },
  none: { borderRadius: 14, paddingHorizontal: 14, paddingVertical: 11 },
  cancel: { alignSelf: 'center', padding: 12 },
  cancelLabel: { fontSize: 16, fontWeight: '600' },
});
