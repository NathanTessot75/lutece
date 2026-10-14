import { Directory, File, Paths } from 'expo-file-system';
import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { listReferenceSamples } from '@/db/monuments';
import { type Theme, useTheme } from '@/lib/theme';

import { cosine } from './likeness';
import { embed, openModel } from './model';
import { referencePhotoUrl } from './pixels';
import { preparePhoto } from './prepare';

// How many reference photos go through the phone's model.
const SAMPLES = 20;
// Below this, the phone does not prepare the photos as the pipeline does.
const SAME = 0.99;

type Result = { title: string; cosine: number; prepareMs: number; embedMs: number };

function mean(values: readonly number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function summarize(results: readonly Result[], totalMs: number) {
  return {
    photos: results.length,
    leastCosine: Math.min(...results.map((result) => result.cosine)),
    meanCosine: mean(results.map((result) => result.cosine)),
    prepareMs: mean(results.map((result) => result.prepareMs)),
    embedMs: mean(results.map((result) => result.embedMs)),
    totalMs,
  };
}

function Summary({ results, loadMs, theme }: { results: Result[]; loadMs: number; theme: Theme }) {
  const least = Math.min(...results.map((result) => result.cosine));
  return (
    <View style={[styles.group, { backgroundColor: theme.surface }]}>
      <Text style={[styles.line, { color: least >= SAME ? theme.text : theme.accent }]}>
        Cosinus avec le pipeline : pire {least.toFixed(4)}, moyen{' '}
        {mean(results.map((result) => result.cosine)).toFixed(4)}
      </Text>
      <Text style={[styles.line, { color: theme.secondaryText }]}>
        Chargement du modèle : {Math.round(loadMs)} ms
      </Text>
      <Text style={[styles.line, { color: theme.secondaryText }]}>
        Par photo : préparation {Math.round(mean(results.map((r) => r.prepareMs)))} ms, calcul{' '}
        {Math.round(mean(results.map((r) => r.embedMs)))} ms
      </Text>
    </View>
  );
}

/**
 * Check that the phone gives the vectors that the pipeline gave (SPEC §6.3):
 * the first photos of a few monuments are downloaded at the width the
 * pipeline read them, prepared and embedded here, and compared with the
 * vectors of the bundle.
 */
export function ModelCheck({ runAtOnce = false }: { runAtOnce?: boolean }) {
  const db = useSQLiteContext();
  const theme = useTheme();
  const [results, setResults] = useState<Result[]>([]);
  const [loadMs, setLoadMs] = useState(0);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setRunning(true);
    setError(null);
    setResults([]);
    try {
      const samples = await listReferenceSamples(db, SAMPLES);
      const started = Date.now();
      const model = await openModel();
      setLoadMs(Date.now() - started);
      const folder = new Directory(Paths.cache, 'model-check');
      folder.create({ intermediates: true, idempotent: true });
      const done: Result[] = [];
      for (const sample of samples) {
        const photo = await File.downloadFileAsync(
          referencePhotoUrl(sample.thumbUrl),
          new File(folder, `${sample.id}.jpg`),
          { idempotent: true },
        );
        const before = Date.now();
        const pixels = await preparePhoto(photo.uri);
        const prepared = Date.now();
        const vector = await embed(model, pixels);
        const embedded = Date.now();
        done.push({
          title: sample.title,
          cosine: cosine(vector, sample),
          prepareMs: prepared - before,
          embedMs: embedded - prepared,
        });
        setResults([...done]);
      }
      // Read on the computer, through the development server.
      console.info('[model check]', JSON.stringify(summarize(done, Date.now() - started)));
    } catch (failure) {
      setError(String(failure));
      console.info('[model check] failed', String(failure));
    } finally {
      setRunning(false);
    }
  }

  const started = useRef(false);
  useEffect(() => {
    if (runAtOnce && !started.current) {
      started.current = true;
      void run();
    }
  });

  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
    >
      <Pressable
        style={[styles.button, { backgroundColor: running ? theme.muted : theme.accent }]}
        onPress={run}
        disabled={running}
        accessibilityRole="button"
      >
        <Text style={[styles.buttonText, { color: theme.onAccent }]}>
          {running ? `En cours (${results.length} / ${SAMPLES})` : 'Lancer la vérification'}
        </Text>
      </Pressable>
      {error && <Text style={[styles.line, { color: theme.accent }]}>{error}</Text>}
      {results.length > 0 && <Summary results={results} loadMs={loadMs} theme={theme} />}
      {results.length > 0 && (
        <View style={[styles.group, { backgroundColor: theme.surface }]}>
          {results.map((result, index) => (
            <Text key={index} style={[styles.line, { color: theme.text }]} numberOfLines={1}>
              {result.cosine.toFixed(4)} · {result.prepareMs + result.embedMs} ms · {result.title}
            </Text>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 16 },
  button: { borderRadius: 12, paddingVertical: 14, alignItems: 'center' },
  buttonText: { fontSize: 17, fontWeight: '600' },
  group: { borderRadius: 12, padding: 12, gap: 6 },
  line: { fontSize: 15 },
});
