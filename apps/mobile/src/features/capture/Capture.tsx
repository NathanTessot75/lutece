import Constants from 'expo-constants';
import { useIsFocused } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useSQLiteContext } from 'expo-sqlite';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BUNDLE_MODEL, BUNDLE_VERSION } from '@/db/bundle';
import {
  type CapturableMonument,
  listCapturableAround,
  listReferenceVectors,
} from '@/db/monuments';
import { usePlayerDatabase } from '@/db/PlayerDatabase';
import { type NewSample, newSampleId } from '@/db/samples';
import { useCollect } from '@/features/collect/CollectProvider';
import { type Label, LabelSample } from '@/features/collect/LabelSample';
import { keepSamplePhoto } from '@/features/collect/photos';
import {
  LABEL_WITHIN_M,
  type LabelChoice,
  describeCandidates,
  describeDecision,
  labelChoices,
} from '@/features/collect/sample';
import { useCaptures } from '@/features/collection/CapturesProvider';
import { pointsFor } from '@/features/game/rarity';
import { parseFootprint } from '@/features/map/footprint';
import { likeness } from '@/features/recognition/likeness';
import { embedPhoto, openModel } from '@/features/recognition/model';
import { type CompassReading, type Position, useLocationAccess } from '@/lib/location';
import { useTabBarRoom } from '@/lib/tabBar';
import { useTheme } from '@/lib/theme';
import { Text } from '@/lib/typography';

import { type Candidate, coneHalfWidth } from './candidates';
import { Captured } from './Captured';
import { type CaptureMessage, CaptureOverlay } from './CaptureOverlay';
import { ChooseMonument } from './ChooseMonument';
import { type Decision, type Refusal, type Scored, decideShot, refuseBeforePhoto } from './decision';
import { sight } from './geometry';
import { keepPhoto } from './photos';
import { type AimTarget, useAim } from './useAim';
import { Viewfinder, type ViewfinderHandle } from './Viewfinder';

/** What the phone knew when the shutter was pressed. */
type Shot = {
  photoUri: string | null;
  position: Position;
  compass: CompassReading | null;
};

/** A sample of the field test set, waiting for its label and its photo to be kept. */
type Draft = Omit<NewSample, 'id' | 'photoFile' | 'labelMonumentId' | 'oblique' | 'hidden'> & {
  photoUri: string | null;
};

/** What the photo says: its vector, and how much it looks like each monument. */
type Seen = {
  vector: Float32Array;
  likeness: (id: string) => number | null;
};

type Stage =
  | { step: 'aiming' }
  | { step: 'labelling'; draft: Draft; choices: LabelChoice[] }
  | { step: 'choosing'; shot: Shot; candidates: Scored<AimTarget>[]; confirm: boolean }
  | { step: 'captured'; monument: CapturableMonument; photoFile: string | null; points: number };

const REFUSALS: Record<Refusal, CaptureMessage> = {
  out_of_reach: { icon: 'mappin.slash', text: 'Aucun monument à portée' },
  not_facing: { icon: 'scope', text: 'Visez le monument' },
  compass_lost: { icon: 'safari', text: 'Boussole perdue : faites des 8' },
  already_captured: { icon: 'checkmark.seal.fill', text: 'Déjà capturé' },
  not_recognised: { icon: 'eye.slash', text: 'Non reconnu : rapprochez-vous' },
  too_far_without_photo: { icon: 'figure.walk', text: 'Sans photo : approchez-vous à 30 m' },
};

// A message stays this long over the camera.
const MESSAGE_MS = 3000;
// Between the shutter and the tabs, and between the monument aimed at and the shutter.
const SHUTTER_GAP = 6;
const AIM_GAP = 14;

/** Aim at a monument, shoot, and add it to the collection. */
export function Capture() {
  const db = useSQLiteContext();
  const playerDb = usePlayerDatabase();
  const theme = useTheme();
  const { byMonument: captured, record: recordCapture } = useCaptures();
  const collect = useCollect();
  const location = useLocationAccess();
  const focused = useIsFocused();
  const { position, compass, candidates } = useAim(location.granted);
  const viewfinder = useRef<ViewfinderHandle>(null);
  const [stage, setStage] = useState<Stage>({ step: 'aiming' });
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [notice, setNotice] = useState<CaptureMessage | null>(null);
  const [busy, setBusy] = useState(false);
  const insets = useSafeAreaInsets();
  const shutterBottom = insets.bottom + useTabBarRoom() + SHUTTER_GAP;

  // The model takes a moment to load: better before the first shot than during it.
  useEffect(() => {
    openModel().catch(() => {
      // It will be loaded again at the first shot.
    });
  }, []);

  // A message goes by itself after a moment.
  useEffect(() => {
    if (refusal === null && notice === null) {
      return;
    }
    const timer = setTimeout(() => {
      setRefusal(null);
      setNotice(null);
    }, MESSAGE_MS);
    return () => clearTimeout(timer);
  }, [refusal, notice]);

  if (!location.granted) {
    return (
      <View style={[styles.message, { backgroundColor: theme.background }]}>
        <Text style={[styles.messageText, { color: theme.secondaryText }]}>
          Pour capturer un monument, Lutèce a besoin de votre position.
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
    const points = pointsFor(monument.rarityTier);
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
      points,
    });
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setStage({ step: 'captured', monument, photoFile, points });
  };

  /** What the photo says of these monuments; nothing to look at without a photo. */
  const lookAt = async (
    photoUri: string | null,
    among: readonly Candidate<AimTarget>[],
  ): Promise<Seen | null> => {
    if (photoUri === null) {
      return null;
    }
    try {
      const [vector, references] = await Promise.all([
        embedPhoto(photoUri),
        listReferenceVectors(db, among.map((candidate) => candidate.target.id)),
      ]);
      return { vector, likeness: (id) => likeness(vector, references.get(id) ?? []) };
    } catch (failure) {
      // The photo cannot vouch for anything: the geometry alone decides, from close by.
      if (__DEV__) {
        console.warn('The photo could not be looked at', failure);
      }
      return null;
    }
  };

  const refuse = (reason: Refusal) => {
    setNotice(null);
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
    setNotice(null);
    try {
      const photoUri = (await viewfinder.current?.takePicture()) ?? null;
      const shot = { photoUri, position, compass };
      const inSight = candidates.filter((candidate) => candidate.inSight);
      const seen = await lookAt(photoUri, inSight);
      await follow(decideShot(candidates, seen?.likeness ?? null, captured), shot);
    } finally {
      setBusy(false);
    }
  };

  /**
   * In collect mode, a shot is a sample of the field test set: the photo is
   * taken even when nothing is in sight, the app works out what it would have
   * done, and the player says what the photo shows. The collection is left alone.
   */
  const collectShot = async () => {
    if (position === null || busy) {
      return;
    }
    setBusy(true);
    setRefusal(null);
    setNotice(null);
    try {
      const photoUri = (await viewfinder.current?.takePicture()) ?? null;
      const takenAt = new Date().toISOString();
      const compassWorks = compass !== null && coneHalfWidth(compass.level) !== null;
      const before = refuseBeforePhoto(candidates, captured, compassWorks);
      const [seen, around] = await Promise.all([
        lookAt(photoUri, candidates),
        listCapturableAround(db, position, LABEL_WITHIN_M, 0),
      ]);
      const decision: Decision<AimTarget> =
        before === null
          ? decideShot(candidates, seen?.likeness ?? null, captured)
          : { kind: 'nothing', reason: before };
      const choices = labelChoices(
        candidates.map((candidate) => ({ ...candidate, title: candidate.target.monument.title })),
        around.map((monument) => ({
          id: monument.id,
          title: monument.title,
          distanceM: sight(position, parseFootprint(monument.footprint)).distanceM,
        })),
      );
      const draft: Draft = {
        takenAt,
        latitude: position.latitude,
        longitude: position.longitude,
        gpsAccuracyM: position.accuracyM,
        headingDeg: compass?.headingDeg ?? null,
        headingLevel: compass?.level ?? null,
        vector: seen?.vector ?? null,
        candidates: describeCandidates(candidates, seen?.likeness ?? null),
        decision: describeDecision(decision),
        bundleVersion: BUNDLE_VERSION,
        model: BUNDLE_MODEL,
        appVersion: Constants.expoConfig?.version ?? 'unknown',
        photoUri,
      };
      setStage({ step: 'labelling', draft, choices });
    } finally {
      setBusy(false);
    }
  };

  const keepSample = async (draft: Draft, label: Label) => {
    const { photoUri, ...known } = draft;
    const id = await newSampleId(playerDb);
    const photoFile = photoUri === null ? null : await keepSamplePhoto(photoUri, id);
    await collect.record({
      ...known,
      id,
      photoFile,
      labelMonumentId: label.monumentId,
      oblique: label.oblique,
      hidden: label.hidden,
    });
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setNotice({
      icon: 'tray.and.arrow.down.fill',
      text: `Photo n° ${collect.samples.length + 1} gardée`,
    });
    setStage({ step: 'aiming' });
  };

  if (stage.step === 'labelling') {
    return (
      <LabelSample
        choices={stage.choices}
        onLabel={(label) => void keepSample(stage.draft, label)}
        onCancel={() => setStage({ step: 'aiming' })}
      />
    );
  }

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
        points={stage.points}
        onContinue={() => setStage({ step: 'aiming' })}
      />
    );
  }

  // The monument aimed at: one still to capture first, else one already captured.
  const inSight = candidates.filter((candidate) => candidate.inSight);
  const aimed =
    inSight.find((candidate) => !captured.has(candidate.target.id)) ?? inSight[0] ?? null;
  return (
    <View style={styles.screen}>
      {focused && <StatusBar style="light" />}
      <Viewfinder ref={viewfinder} active={focused} />
      <CaptureOverlay
        compass={compass}
        aimed={aimed && { candidate: aimed, captured: captured.has(aimed.target.id) }}
        waiting={busy ? 'photo' : position === null ? 'position' : null}
        message={refusal !== null ? REFUSALS[refusal] : notice}
        collected={collect.enabled ? collect.samples.length : null}
        aimBottom={shutterBottom + SHUTTER_SIZE + AIM_GAP}
      />
      <Pressable
        style={[styles.shutter, { bottom: shutterBottom }, busy && styles.busy]}
        onPress={() => void (collect.enabled ? collectShot() : shoot())}
        disabled={busy}
        accessibilityRole="button"
        accessibilityLabel="Capturer"
      >
        {({ pressed }) => <View style={[styles.shutterCore, pressed && styles.shutterDown]} />}
      </Pressable>
    </View>
  );
}

const SHUTTER_SIZE = 72;

const styles = StyleSheet.create({
  // Black under the camera, in both appearances of the phone.
  screen: {
    flex: 1,
    backgroundColor: '#000000',
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
  // The shutter of a camera, all white: a ring, and a disc that sinks under
  // the thumb. It sits low, above the tabs.
  shutter: {
    position: 'absolute',
    alignSelf: 'center',
    width: SHUTTER_SIZE,
    height: SHUTTER_SIZE,
    borderRadius: SHUTTER_SIZE / 2,
    borderWidth: 4,
    borderColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  shutterCore: {
    width: SHUTTER_SIZE - 16,
    height: SHUTTER_SIZE - 16,
    borderRadius: (SHUTTER_SIZE - 16) / 2,
    backgroundColor: '#FFFFFF',
  },
  shutterDown: {
    transform: [{ scale: 0.88 }],
  },
  busy: {
    opacity: 0.5,
  },
});
