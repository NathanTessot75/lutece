import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import type { MonumentSummary } from '@/db/monuments';
import { describeMonument } from '@/features/monuments/describe';
import { useOpenMonument } from '@/features/monuments/useOpenMonument';
import { useTheme } from '@/lib/theme';

import { photoUri } from './photos';

type Props = {
  monument: MonumentSummary;
  photoFile: string | null;
  onContinue: () => void;
};

/** The monument is in the collection: the moment a capture is for. */
export function Captured({ monument, photoFile, onContinue }: Props) {
  const theme = useTheme();
  const open = useOpenMonument();
  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
    >
      <Text style={[styles.cheer, { color: theme.accent }]}>Capturé !</Text>
      {photoFile !== null && (
        <Image
          source={{ uri: photoUri(photoFile) }}
          style={[styles.photo, { backgroundColor: theme.separator }]}
          resizeMode="cover"
          accessibilityIgnoresInvertColors
        />
      )}
      <Text style={[styles.title, { color: theme.text }]}>{monument.title}</Text>
      <Text style={[styles.details, { color: theme.secondaryText }]}>
        {describeMonument(monument)}
      </Text>
      <View style={styles.actions}>
        <Pressable
          style={[styles.button, { backgroundColor: theme.accent }]}
          onPress={onContinue}
          accessibilityRole="button"
        >
          <Text style={[styles.buttonLabel, { color: theme.onAccent }]}>Continuer</Text>
        </Pressable>
        <Pressable
          style={[styles.button, { backgroundColor: theme.surface }]}
          onPress={() => open(monument.id)}
          accessibilityRole="button"
        >
          <Text style={[styles.buttonLabel, { color: theme.accent }]}>Voir la fiche</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    alignItems: 'center',
    padding: 24,
    gap: 10,
  },
  cheer: {
    fontSize: 34,
    fontWeight: '800',
    marginBottom: 6,
  },
  photo: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: 18,
    marginBottom: 8,
  },
  title: {
    fontSize: 22,
    fontWeight: '700',
    textAlign: 'center',
  },
  details: {
    fontSize: 15,
    textAlign: 'center',
  },
  actions: {
    alignSelf: 'stretch',
    gap: 10,
    marginTop: 18,
  },
  button: {
    alignItems: 'center',
    borderRadius: 14,
    paddingVertical: 14,
  },
  buttonLabel: {
    fontSize: 17,
    fontWeight: '600',
  },
});
