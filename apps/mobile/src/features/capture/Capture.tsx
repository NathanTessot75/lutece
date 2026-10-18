import { useIsFocused } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { type CapturableMonument, listReferenceVectors } from '@/db/monuments';
import { useCaptures } from '@/features/collection/CapturesProvider';
import { likeness } from '@/features/recognition/likeness';
import { embedPhoto, openModel } from '@/features/recognition/model';
import { type CompassReading, type Position, useLocationAccess } from '@/lib/location';
import { useTheme } from '@/lib/theme';

import { CandidateList } from './CandidateList';
import { type Candidate, coneHalfWidth } from './candidates';
import { Captured } from './Captured';
import { ChooseMonument } from './ChooseMonument';
import { type Decision, type Refusal, type Scored, decideShot, refuseBeforePhoto } from './decision';
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
  | { step: 'choosing'; shot: Shot; candidates: Scored<AimTarget>[]; confirm: boolean }
  | { step: 'captured'; monument: CapturableMonument; photoFile: string | null };

const REFUSALS: Record<Refusal, string> = {
  out_of_reach: 'Aucun monument à capturer ici : approche-toi d’un monument.',
  not_facing: 'Tourne-toi vers le monument : il doit être dans le viseur.',
  compass_lost: 'La boussole est perdue : fais des 8 avec le téléphone, puis réessaie.',
  already_captured: 'Tu as déjà capturé ce monument.',
  not_recognised: 'Lutèce ne reconnaît pas de monument sur ta photo : rapproche-toi ou vise sa façade.',
  too_far_without_photo: 'Sans photo, Lutèce ne peut vérifier qu’à moins de 30 m : approche-toi.',
};

/** Aim at a monument, shoot, and add it to the collection. */
export function Capture() {
  const db = useSQLiteContext();
  const theme = useTheme();
  const { byMonument: captured, record: recordCapture } = useCaptures();
  const location = useLocationAccess();
  const focused = useIsFocused();
  const { position, compass, candidates } = useAim(location.granted);
  const viewfinder = useRef<ViewfinderHandle>(null);
  const [stage, setStage] = useState<Stage>({ step: 'aiming' });
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [busy, setBusy] = useState(false);

  // The model takes a moment to load: better before the first shot than during it.
  useEffect(() => {
    openModel().catch(() => {
      // It will be loaded again at the first shot.
    });
  }, []);

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

  const record = async (candidate: Scored<AimTarget>, shot: Shot, chosenByPlayer: boolean) => {
    const { monument } = candidate.target;
    const photoFile = shot.photoUri === null ? null : await keepPhoto(shot.photoUri, monument.id);
    await recordCapture({
      monumentId: monument.id,
      latitude: shot.position.latitude,
      longitude: shot.position.longitude,
      gpsAccuracyM: shot.position.accuracyM,
      headingDeg: shot.compass?.headingDeg ?? null,
      headingLevel: shot.compass?.level ?? null,
      geoScore: candidate.score,
      imageScore: candidate.likeness,
      chosenByPlayer,
      photoFile,
    });
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setStage({ step: 'captured', monument, photoFile });
  };

  /** How much the photo looks like each monument in sight; nothing to look at without a photo. */
  const lookAt = async (
    photoUri: string | null,
    inSight: readonly Candidate<AimTarget>[],
  ): Promise<((id: string) => number | null) | null> => {
    if (photoUri === null) {
      return null;
    }
    try {
      const [vector, references] = await Promise.all([
        embedPhoto(photoUri),
        listReferenceVectors(db, inSight.map((candidate) => candidate.target.id)),
      ]);
      return (id) => likeness(vector, references.get(id) ?? []);
    } catch (failure) {
      // The photo cannot vouch for anything: the geometry alone decides, from close by.
      if (__DEV__) {
        console.warn('The photo could not be looked at', failure);
      }
      return null;
    }
  };

  const refuse = (reason: Refusal) => {
    setRefusal(reason);
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
  };

  const follow = async (decision: Decision<AimTarget>, shot: Shot) => {
    switch (decision.kind) {
      case 'nothing':
        refuse(decision.reason);
        return;
      case 'capture':
        await record(decision.candidate, shot, false);
        return;
      case 'choose':
      case 'confirm':
        setStage({
          step: 'choosing',
          shot,
          candidates: decision.candidates,
          confirm: decision.kind === 'confirm',
        });
    }
  };

  const shoot = async () => {
    if (position === null || busy) {
      return;
    }
    const compassWorks = compass !== null && coneHalfWidth(compass.level) !== null;
    const before = refuseBeforePhoto(candidates, captured, compassWorks);
    if (before !== null) {
      refuse(before);
      return;
    }
    setBusy(true);
    setRefusal(null);
    try {
      const photoUri = (await viewfinder.current?.takePicture()) ?? null;
      const shot = { photoUri, position, compass };
      const inSight = candidates.filter((candidate) => candidate.inSight);
      const looks = await lookAt(photoUri, inSight);
      await follow(decideShot(candidates, looks, captured), shot);
    } finally {
      setBusy(false);
    }
  };

  if (stage.step === 'choosing') {
    return (
      <ChooseMonument
        candidates={stage.candidates}
        confirm={stage.confirm}
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
  const label = busy
    ? 'Je regarde ta photo…'
    : aimed
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
