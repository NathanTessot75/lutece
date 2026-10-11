import { useIsFocused } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { listCapturedIds, saveCapture } from '@/db/captures';
import type { CapturableMonument } from '@/db/monuments';
import { usePlayerDatabase } from '@/db/PlayerDatabase';
import { type CompassReading, type Position, useLocationAccess } from '@/lib/location';
import { useTheme } from '@/lib/theme';

import { CandidateList } from './CandidateList';
import { type Candidate, coneHalfWidth } from './candidates';
import { Captured } from './Captured';
import { ChooseMonument } from './ChooseMonument';
import { type Refusal, decide } from './decision';
import { describeCandidate } from './describe';
import { keepPhoto } from './photos';
import { type AimTarget, useAim } from './useAim';
import { Viewfinder, type ViewfinderHandle } from './Viewfinder';

/** What the phone knew when the shutter was pressed. */
type Shot = {
  photoUri: string | null;
  position: Position;
  compass: CompassReading | null;
};

type Stage =
  | { step: 'aiming' }
  | { step: 'choosing'; shot: Shot; candidates: Candidate<AimTarget>[] }
  | { step: 'captured'; monument: CapturableMonument; photoFile: string | null };

const REFUSALS: Record<Refusal, string> = {
  out_of_reach: 'Aucun monument à capturer ici : approche-toi d’un monument.',
  not_facing: 'Tourne-toi vers le monument : il doit être dans le viseur.',
  compass_lost: 'La boussole est perdue : fais des 8 avec le téléphone, puis réessaie.',
  already_captured: 'Tu as déjà capturé ce monument.',
};

/** Aim at a monument, shoot, and add it to the collection. */
export function Capture() {
  const theme = useTheme();
  const playerDb = usePlayerDatabase();
  const location = useLocationAccess();
  const focused = useIsFocused();
  const { position, compass, candidates } = useAim(location.granted);
  const viewfinder = useRef<ViewfinderHandle>(null);
  const [captured, setCaptured] = useState<ReadonlySet<string>>(new Set());
  const [stage, setStage] = useState<Stage>({ step: 'aiming' });
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let current = true;
    void listCapturedIds(playerDb).then((ids) => {
      if (current) {
        setCaptured(ids);
      }
    });
    return () => {
      current = false;
    };
  }, [playerDb]);

  if (!location.granted) {
    return (
      <View style={[styles.message, { backgroundColor: theme.background }]}>
        <Text style={[styles.messageText, { color: theme.secondaryText }]}>
          Pour capturer un monument, Lutèce a besoin de ta position.
        </Text>
        <Pressable
          style={[styles.button, { backgroundColor: theme.accent }]}
          onPress={location.ask}
          accessibilityRole="button"
        >
          <Text style={[styles.buttonLabel, { color: theme.onAccent }]}>Activer ma position</Text>
        </Pressable>
      </View>
    );
  }

  const record = async (candidate: Candidate<AimTarget>, shot: Shot, chosenByPlayer: boolean) => {
    const { monument } = candidate.target;
    const photoFile = shot.photoUri === null ? null : await keepPhoto(shot.photoUri, monument.id);
    await saveCapture(playerDb, {
      monumentId: monument.id,
      latitude: shot.position.latitude,
      longitude: shot.position.longitude,
      gpsAccuracyM: shot.position.accuracyM,
      headingDeg: shot.compass?.headingDeg ?? null,
      headingLevel: shot.compass?.level ?? null,
      geoScore: candidate.score,
      chosenByPlayer,
      photoFile,
    });
    setCaptured((known) => new Set(known).add(monument.id));
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setStage({ step: 'captured', monument, photoFile });
  };

  const shoot = async () => {
    if (position === null || busy) {
      return;
    }
    const compassWorks = compass !== null && coneHalfWidth(compass.level) !== null;
    const decision = decide(candidates, captured, compassWorks);
    if (decision.kind === 'nothing') {
      setRefusal(decision.reason);
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      return;
    }
    setBusy(true);
    setRefusal(null);
    try {
      const photoUri = (await viewfinder.current?.takePicture()) ?? null;
      const shot = { photoUri, position, compass };
      if (decision.kind === 'capture') {
        await record(decision.candidate, shot, false);
      } else {
        setStage({ step: 'choosing', shot, candidates: decision.candidates });
      }
    } finally {
      setBusy(false);
    }
  };

  if (stage.step === 'choosing') {
    return (
      <ChooseMonument
        candidates={stage.candidates}
        onChoose={(candidate) => void record(candidate, stage.shot, true)}
        onCancel={() => setStage({ step: 'aiming' })}
      />
    );
  }
  if (stage.step === 'captured') {
    return (
      <Captured
        monument={stage.monument}
        photoFile={stage.photoFile}
        onContinue={() => setStage({ step: 'aiming' })}
      />
    );
  }

  const aimed = candidates.find(
    (candidate) => candidate.inSight && !captured.has(candidate.target.id),
  );
  const label = aimed
    ? `${aimed.target.monument.title}\n${describeCandidate(aimed)}`
    : position === null
      ? 'Recherche de ta position…'
      : 'Vise un monument';
  return (
    <View style={[styles.screen, { backgroundColor: theme.background }]}>
      <View style={styles.top}>
        <Viewfinder ref={viewfinder} active={focused} label={label} />
        <Pressable
          style={[styles.shutter, { borderColor: theme.background }, busy && styles.pressed]}
          onPress={() => void shoot()}
          disabled={busy}
          accessibilityRole="button"
          accessibilityLabel="Capturer"
        >
          <View style={[styles.shutterCore, { backgroundColor: theme.accent }]} />
        </Pressable>
      </View>
      {refusal !== null && (
        <Text style={[styles.refusal, { color: theme.text, backgroundColor: theme.surface }]}>
          {REFUSALS[refusal]}
        </Text>
      )}
      <CandidateList
        position={position}
        compass={compass}
        candidates={candidates}
        captured={captured}
      />
    </View>
  );
}

const SHUTTER_SIZE = 72;

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  message: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
    padding: 32,
  },
  messageText: {
    fontSize: 16,
    textAlign: 'center',
  },
  button: {
    borderRadius: 22,
    paddingHorizontal: 18,
    paddingVertical: 11,
  },
  buttonLabel: {
    fontSize: 16,
    fontWeight: '600',
  },
  // The shutter sits astride the lower edge of the viewfinder: the room left
  // under the viewfinder keeps all of it within reach of a finger.
  top: {
    paddingBottom: SHUTTER_SIZE / 2,
  },
  shutter: {
    position: 'absolute',
    alignSelf: 'center',
    bottom: 0,
    width: SHUTTER_SIZE,
    height: SHUTTER_SIZE,
    borderRadius: SHUTTER_SIZE / 2,
    borderWidth: 5,
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  shutterCore: {
    width: SHUTTER_SIZE - 22,
    height: SHUTTER_SIZE - 22,
    borderRadius: (SHUTTER_SIZE - 22) / 2,
  },
  pressed: {
    opacity: 0.5,
  },
  refusal: {
    marginHorizontal: 16,
    marginTop: 10,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    overflow: 'hidden',
  },
});
