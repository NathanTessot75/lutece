import { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import { formatCount } from '@/lib/format';
import { type Theme, useTheme } from '@/lib/theme';

import { useContribution } from './ContributeProvider';

function photos(count: number): string {
  return `${formatCount(count)} ${count > 1 ? 'photos' : 'photo'}`;
}

function Section({ title, children, theme }: { title: string; children: string; theme: Theme }) {
  return (
    <View style={styles.section}>
      <Text style={[styles.heading, { color: theme.text }]}>{title}</Text>
      <Text style={[styles.note, { color: theme.secondaryText }]}>{children}</Text>
    </View>
  );
}

/** What contributing sends, the switch to agree, and the way to take it all back. */
export function ContributeSettings() {
  const theme = useTheme();
  const { available, enabled, setEnabled, sent, waiting, sending, failed, retry, erase } =
    useContribution();
  const [erasing, setErasing] = useState(false);

  const confirmErase = () =>
    Alert.alert(
      'Supprimer tes contributions ?',
      `Les ${photos(sent)} envoyées seront effacées du serveur avec leurs informations, et la contribution s’arrêtera. Ta collection reste sur le téléphone.`,
      [
        { text: 'Annuler', style: 'cancel' },
        {
          text: 'Supprimer',
          style: 'destructive',
          onPress: () => {
            setErasing(true);
            erase()
              .catch(() =>
                Alert.alert(
                  'Suppression impossible',
                  'Le serveur n’a pas répondu. Vérifie ta connexion et réessaie.',
                ),
              )
              .finally(() => setErasing(false));
          },
        },
      ],
    );

  if (!available) {
    return (
      <ScrollView
        style={{ backgroundColor: theme.background }}
        contentInsetAdjustmentBehavior="automatic"
        contentContainerStyle={styles.content}
      >
        <Text style={[styles.note, { color: theme.secondaryText }]}>
          Cette version de Lutèce n’envoie rien : elle ne connaît aucun serveur.
        </Text>
      </ScrollView>
    );
  }

  let status: string | null = null;
  if (erasing) {
    status = 'Suppression en cours…';
  } else if (sending) {
    status = 'Envoi en cours…';
  } else if (enabled) {
    status = `${photos(sent)} envoyée${sent > 1 ? 's' : ''} · ${formatCount(waiting)} en attente`;
  } else if (sent > 0) {
    status = `${photos(sent)} envoyée${sent > 1 ? 's' : ''}`;
  }
  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
    >
      <Text style={[styles.lead, { color: theme.text }]}>
        Envoie tes photos pour aider Lutèce à mieux reconnaître les monuments. C’est facultatif : tu
        peux arrêter et tout supprimer quand tu veux.
      </Text>
      <Section title="Ce qui part" theme={theme}>
        Chaque photo prise pour une capture ou en mode collecte, réduite à 1 600 pixels, y compris
        celles déjà prises. Avec elle : l’heure, ta position et ton cap au moment de la photo, et ce
        que Lutèce a reconnu. Ta position dit où tu étais et quand.
      </Section>
      <Section title="Qui les reçoit" theme={theme}>
        Le développeur de Lutèce, sur un serveur Supabase en Europe (Paris). Elles ne sont pas
        publiques : elles servent à mesurer et à améliorer la reconnaissance.
      </Section>
      <Section title="Sans compte" theme={theme}>
        Lutèce te donne un identifiant anonyme, sans nom ni adresse e-mail, gardé sur ce téléphone.
        Si tu supprimes l’app, tu ne pourras plus effacer tes photos : supprime-les d’abord ici.
      </Section>
      <Section title="Les autres" theme={theme}>
        Évite de photographier des personnes de près : leur visage partirait avec la photo.
      </Section>
      <Pressable
        style={[styles.group, styles.switchRow, { backgroundColor: theme.surface }]}
        onPress={() => void setEnabled(!enabled)}
        disabled={erasing}
        accessibilityRole="switch"
        accessibilityState={{ checked: enabled, disabled: erasing }}
      >
        <Text style={[styles.title, { color: theme.text }]}>Contribuer mes photos</Text>
        <Switch
          value={enabled}
          onValueChange={(next) => void setEnabled(next)}
          disabled={erasing}
          trackColor={{ true: theme.accent }}
        />
      </Pressable>
      {status !== null && <Text style={[styles.status, { color: theme.text }]}>{status}</Text>}
      {enabled && failed !== null && !sending && (
        <View style={styles.section}>
          <Text style={[styles.note, { color: theme.secondaryText }]}>
            Le dernier envoi a échoué (pas de réseau ?). Lutèce réessaiera à ton retour dans l’app.
          </Text>
          <Pressable onPress={retry} accessibilityRole="button" hitSlop={8}>
            <Text style={[styles.action, { color: theme.accent }]}>Réessayer</Text>
          </Pressable>
        </View>
      )}
      {sent > 0 && (
        <Pressable
          style={[styles.group, styles.button, { backgroundColor: theme.surface }]}
          onPress={confirmErase}
          disabled={erasing}
          accessibilityRole="button"
          accessibilityState={{ disabled: erasing }}
        >
          <Text style={[styles.action, { color: theme.accent }]}>Supprimer mes contributions</Text>
        </Pressable>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 12 },
  lead: { fontSize: 16, lineHeight: 22 },
  section: { gap: 4 },
  heading: { fontSize: 15, fontWeight: '600' },
  note: { fontSize: 14, lineHeight: 20 },
  group: { borderRadius: 14, overflow: 'hidden' },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginTop: 8,
  },
  title: { fontSize: 17, fontWeight: '600' },
  status: { fontSize: 15 },
  button: { paddingHorizontal: 14, paddingVertical: 12, marginTop: 8 },
  action: { fontSize: 17 },
});
