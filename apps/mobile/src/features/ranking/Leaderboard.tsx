import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';

import { formatPoints } from '@/features/game/rarity';
import { formatCount } from '@/lib/format';
import { supabase } from '@/lib/supabase';
import { type Theme, useTheme } from '@/lib/theme';
import { Text, fonts } from '@/lib/typography';

import { useRanking } from './RankingProvider';
import { type Period, PseudonymRefused, type Standing, fetchLeaderboard } from './send';
import { formatWeekLeft, untilNextWeek } from './week';

const ARRONDISSEMENTS = Array.from({ length: 20 }, (_, index) => index + 1);
const PERIODS: { value: Period; label: string }[] = [
  { value: 'week', label: 'Semaine' },
  { value: 'all', label: 'Général' },
];

/** The week or all time, as two halves of a pill. */
function PeriodSwitch({
  period,
  onChange,
  theme,
}: {
  period: Period;
  onChange: (period: Period) => void;
  theme: Theme;
}) {
  return (
    <View style={[styles.periods, { backgroundColor: theme.surface }]}>
      {PERIODS.map(({ value, label }) => {
        const chosen = value === period;
        return (
          <Pressable
            key={value}
            style={[styles.period, chosen && { backgroundColor: theme.accent }]}
            onPress={() => onChange(value)}
            accessibilityRole="button"
            accessibilityState={{ selected: chosen }}
          >
            <Text style={[styles.periodLabel, { color: chosen ? theme.onAccent : theme.text }]}>
              {label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function Section({ title, children, theme }: { title: string; children: string; theme: Theme }) {
  return (
    <View style={styles.section}>
      <Text style={[styles.heading, { color: theme.text }]}>{title}</Text>
      <Text style={[styles.note, { color: theme.secondaryText }]}>{children}</Text>
    </View>
  );
}

/** What taking part means, a pseudonym, and the switch to join. */
function Join({ theme }: { theme: Theme }) {
  const { join } = useRanking();
  const [name, setName] = useState('');
  const [joining, setJoining] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const submit = () => {
    const username = name.trim();
    if (username.length < 3 || username.length > 20) {
      setProblem('Un pseudonyme a de 3 à 20 caractères.');
      return;
    }
    setJoining(true);
    setProblem(null);
    join(username)
      .catch((error: unknown) =>
        setProblem(
          error instanceof PseudonymRefused
            ? error.message
            : 'Impossible de rejoindre les classements pour l’instant (pas de réseau ?).',
        ),
      )
      .finally(() => setJoining(false));
  };

  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Text style={[styles.lead, { color: theme.text }]}>
        Comparez vos points avec ceux des autres joueurs, pour tout Paris et par arrondissement.
        C’est facultatif.
      </Text>
      <Section title="Ce qui part" theme={theme}>
        Pour chaque capture : le monument, l’heure, votre position et ce que Lutèce a mesuré, pour
        vérifier que vous étiez sur place. Pas vos photos : elles ne partent que si vous
        contribuez. Vos captures déjà faites partent aussi.
      </Section>
      <Section title="Qui voit quoi" theme={theme}>
        Les autres joueurs voient votre pseudonyme, vos points et votre nombre de captures, jamais
        où ni quand vous avez capturé. Le développeur de Lutèce voit tout, pour vérifier les captures
        douteuses : elles ne comptent qu’une fois validées.
      </Section>
      <Section title="Sans compte" theme={theme}>
        Votre inscription est liée à ce téléphone : si vous en changez ou si vous supprimez l’app,
        vous repartez de zéro. Vous pouvez quitter les classements quand vous voulez, votre
        pseudonyme et vos captures sont alors effacés du serveur.
      </Section>
      <TextInput
        style={[styles.input, { backgroundColor: theme.surface, color: theme.text }]}
        value={name}
        onChangeText={setName}
        placeholder="Votre pseudonyme"
        placeholderTextColor={theme.secondaryText}
        maxLength={20}
        autoCorrect={false}
        autoCapitalize="none"
        returnKeyType="done"
        onSubmitEditing={submit}
        editable={!joining}
        accessibilityLabel="Pseudonyme"
      />
      {problem !== null && <Text style={[styles.problem, { color: theme.accent }]}>{problem}</Text>}
      <Pressable
        style={[styles.button, { backgroundColor: theme.accent, opacity: joining ? 0.6 : 1 }]}
        onPress={submit}
        disabled={joining}
        accessibilityRole="button"
      >
        <Text style={[styles.buttonLabel, { color: theme.onAccent }]}>
          {joining ? 'Inscription…' : 'Rejoindre les classements'}
        </Text>
      </Pressable>
    </ScrollView>
  );
}

function Row({ standing, theme }: { standing: Standing; theme: Theme }) {
  const text = standing.isMe ? theme.onAccent : theme.text;
  const secondary = standing.isMe ? theme.onAccent : theme.secondaryText;
  return (
    <View
      style={[
        styles.row,
        { backgroundColor: standing.isMe ? theme.accent : theme.surface, borderColor: theme.separator },
      ]}
    >
      <Text style={[styles.rank, { color: text }]}>{standing.rank}</Text>
      <View style={styles.who}>
        <Text style={[styles.username, { color: text }]} numberOfLines={1}>
          {standing.username}
        </Text>
        <Text style={[styles.captures, { color: secondary }]}>
          {formatCount(standing.captures)} {standing.captures > 1 ? 'captures' : 'capture'}
        </Text>
      </View>
      <Text style={[styles.points, { color: text }]}>{formatPoints(standing.points)}</Text>
    </View>
  );
}

function summary(counts: ReturnType<typeof useRanking>['counts']): string {
  const parts = [
    `${formatCount(counts.accepted)} ${counts.accepted > 1 ? 'comptées' : 'comptée'}`,
  ];
  if (counts.pending_review > 0) {
    parts.push(`${formatCount(counts.pending_review)} en attente de vérification`);
  }
  if (counts.rejected > 0) {
    parts.push(`${formatCount(counts.rejected)} ${counts.rejected > 1 ? 'refusées' : 'refusée'}`);
  }
  if (counts.waiting > 0) {
    parts.push(`${formatCount(counts.waiting)} à envoyer`);
  }
  return `Vos captures : ${parts.join(' · ')}`;
}

/**
 * The leaderboard of Paris or of an arrondissement, of the week or of all
 * time, and the player's own standing.
 */
function Board({ theme }: { theme: Theme }) {
  const { username, counts, sending, failed, retry, leave, round } = useRanking();
  const [period, setPeriod] = useState<Period>('week');
  const [scope, setScope] = useState<number | null>(null);
  const [standings, setStandings] = useState<Standing[] | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [asked, setAsked] = useState(0);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    if (supabase === null) {
      return;
    }
    let current = true;
    void fetchLeaderboard(supabase, scope, period)
      .then((found) => {
        if (current) {
          setStandings(found);
          setUnreachable(false);
        }
      })
      .catch(() => {
        if (current) {
          setUnreachable(true);
        }
      });
    return () => {
      current = false;
    };
  }, [scope, period, round, asked]);
  // Back on the screen: the others may have captured meanwhile.
  useFocusEffect(useCallback(() => setAsked((value) => value + 1), []));

  const choosePeriod = (value: Period) => {
    setPeriod(value);
    // The standings of the other period would show under the new title.
    setStandings(null);
  };

  const confirmLeave = () =>
    Alert.alert(
      'Quitter les classements ?',
      'Votre pseudonyme et vos captures seront effacés du serveur. Votre collection reste sur le téléphone.',
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Quitter',
          style: 'destructive',
          onPress: () => {
            setLeaving(true);
            leave()
              .catch(() =>
                Alert.alert('Impossible de quitter', 'Le serveur n’a pas répondu. Réessayez plus tard.'),
              )
              .finally(() => setLeaving(false));
          },
        },
      ],
    );

  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.board}
    >
      <PeriodSwitch period={period} onChange={choosePeriod} theme={theme} />
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scopes}
      >
        {[null, ...ARRONDISSEMENTS].map((value) => {
          const chosen = value === scope;
          return (
            <Pressable
              key={value ?? 'paris'}
              style={[styles.scope, { backgroundColor: chosen ? theme.accent : theme.surface }]}
              onPress={() => setScope(value)}
              accessibilityRole="button"
              accessibilityState={{ selected: chosen }}
            >
              <Text style={[styles.scopeLabel, { color: chosen ? theme.onAccent : theme.text }]}>
                {value === null ? 'Paris' : `${value}${value === 1 ? 'er' : 'e'}`}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
      {period === 'week' && (
        <Text style={[styles.reset, styles.note, { color: theme.secondaryText }]}>
          Remise à zéro dans {formatWeekLeft(untilNextWeek(new Date()))}, lundi à minuit.
        </Text>
      )}

      {unreachable ? (
        <View style={styles.message}>
          <Text style={[styles.note, { color: theme.secondaryText }]}>
            Classement indisponible pour l’instant (pas de réseau ?).
          </Text>
          <Pressable onPress={() => setAsked((value) => value + 1)} accessibilityRole="button" hitSlop={8}>
            <Text style={[styles.action, { color: theme.accent }]}>Réessayer</Text>
          </Pressable>
        </View>
      ) : standings === null ? (
        <Text style={[styles.message, styles.note, { color: theme.secondaryText }]}>Chargement…</Text>
      ) : standings.length === 0 ? (
        <Text style={[styles.message, styles.note, { color: theme.secondaryText }]}>
          {period === 'week'
            ? 'Personne n’a encore de capture comptée ici cette semaine.'
            : 'Personne n’a encore de capture comptée ici.'}
        </Text>
      ) : (
        <View style={styles.list}>
          {standings.map((standing) => (
            <Row key={`${standing.rank}-${standing.username}`} standing={standing} theme={theme} />
          ))}
        </View>
      )}
      {period === 'week' &&
        !unreachable &&
        standings !== null &&
        standings.length > 0 &&
        !standings.some((standing) => standing.isMe) && (
          <Text style={[styles.message, styles.note, { color: theme.secondaryText }]}>
            Vous n’avez pas encore de capture comptée ici cette semaine.
          </Text>
        )}

      <View style={styles.footer}>
        <Text style={[styles.note, { color: theme.secondaryText }]}>
          Vous jouez sous le pseudonyme « {username} ».
        </Text>
        <Text style={[styles.note, { color: theme.secondaryText }]}>
          {sending ? 'Envoi de vos captures…' : summary(counts)}
        </Text>
        {counts.pending_review > 0 && (
          <Text style={[styles.note, { color: theme.secondaryText }]}>
            Une capture en attente compte dès que le développeur de Lutèce la valide.
          </Text>
        )}
        {failed !== null && !sending && (
          <View style={styles.section}>
            <Text style={[styles.note, { color: theme.secondaryText }]}>
              Le dernier envoi a échoué (pas de réseau ?). Lutèce réessaiera à votre retour dans l’app.
            </Text>
            <Pressable onPress={retry} accessibilityRole="button" hitSlop={8}>
              <Text style={[styles.action, { color: theme.accent }]}>Réessayer</Text>
            </Pressable>
          </View>
        )}
        <Pressable
          style={[styles.button, styles.leave, { backgroundColor: theme.surface }]}
          onPress={confirmLeave}
          disabled={leaving}
          accessibilityRole="button"
        >
          <Text style={[styles.action, { color: theme.accent }]}>
            {leaving ? 'Départ…' : 'Quitter les classements'}
          </Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

/** The leaderboards: joining them first, then the standings. */
export function Leaderboard() {
  const theme = useTheme();
  const { available, username } = useRanking();
  if (!available) {
    return (
      <ScrollView
        style={{ backgroundColor: theme.background }}
        contentInsetAdjustmentBehavior="automatic"
        contentContainerStyle={styles.content}
      >
        <Text style={[styles.note, { color: theme.secondaryText }]}>
          Cette version de Lutèce n’a pas de classement : elle ne connaît aucun serveur.
        </Text>
      </ScrollView>
    );
  }
  return username === null ? <Join theme={theme} /> : <Board theme={theme} />;
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 12 },
  lead: { fontSize: 16, lineHeight: 22 },
  section: { gap: 4 },
  heading: { fontSize: 15, fontWeight: '600' },
  note: { fontSize: 14, lineHeight: 20 },
  input: {
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontFamily: fonts.regular,
    fontSize: 17,
    marginTop: 8,
  },
  problem: { fontSize: 14 },
  button: { alignItems: 'center', borderRadius: 14, paddingVertical: 14 },
  buttonLabel: { fontSize: 17, fontWeight: '600' },
  board: { paddingBottom: 32 },
  periods: {
    flexDirection: 'row',
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 999,
    padding: 3,
  },
  period: { flex: 1, alignItems: 'center', borderRadius: 999, paddingVertical: 8 },
  periodLabel: { fontSize: 15, fontWeight: '600' },
  reset: { paddingHorizontal: 16, paddingBottom: 4 },
  scopes: { paddingHorizontal: 16, paddingVertical: 12, gap: 8 },
  scope: { borderRadius: 16, paddingHorizontal: 14, paddingVertical: 7 },
  scopeLabel: { fontSize: 15, fontWeight: '600' },
  message: { paddingHorizontal: 16, paddingVertical: 12, gap: 6 },
  list: { marginHorizontal: 16, borderRadius: 12, overflow: 'hidden' },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  rank: { width: 32, fontSize: 17, fontWeight: '700', fontVariant: ['tabular-nums'] },
  who: { flex: 1 },
  username: { fontSize: 16, fontWeight: '600' },
  captures: { fontSize: 13, marginTop: 1 },
  points: { fontSize: 15, fontWeight: '600', fontVariant: ['tabular-nums'] },
  footer: { paddingHorizontal: 16, paddingTop: 20, gap: 8 },
  action: { fontSize: 17 },
  leave: { marginTop: 8 },
});
