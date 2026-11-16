import { type SFSymbol, SymbolView } from 'expo-symbols';
import { useEffect } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, {
  FadeIn,
  FadeInUp,
  FadeOut,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { pointsFor } from '@/features/game/rarity';
import { useOpenMonument } from '@/features/monuments/useOpenMonument';
import { formatDistance, formatHeading } from '@/lib/format';
import type { CompassReading } from '@/lib/location';
import { useNightTabBar } from '@/lib/tabBar';
import { NIGHT } from '@/lib/theme';
import { Text, fonts } from '@/lib/typography';

import type { Candidate } from './candidates';
import { turn } from './geometry';
import type { AimTarget } from './useAim';

/** A short word for the player, with its icon. */
export type CaptureMessage = {
  icon: SFSymbol;
  text: string;
};

/** The monument in the viewfinder, and whether it is already in the collection. */
export type Aimed = {
  candidate: Candidate<AimTarget>;
  captured: boolean;
};

type Props = {
  compass: CompassReading | null;
  aimed: Aimed | null;
  /** What the capture waits for, if anything. */
  waiting: 'position' | 'photo' | null;
  message: CaptureMessage | null;
  /** The photos kept for the test set, in collect mode. */
  collected: number | null;
  /** Where the monument aimed at is written, above the shutter. */
  aimBottom: number;
};

// The needle of the « safari » symbol points to the north-east.
const NEEDLE_DEG = 45;
const TURN_MS = 150;
// The monument drawn in the middle, and the corners of the square around it.
const MARK_SIZE = 160;
const FRAME_SIZE = 230;
const CORNER = 30;
const LINE = 4;

/** A compass whose needle keeps to the north while the phone turns. */
function Compass({ reading }: { reading: CompassReading | null }) {
  const angle = useSharedValue(-NEEDLE_DEG);
  const heading = reading?.headingDeg ?? null;
  useEffect(() => {
    if (heading === null) {
      return;
    }
    const current = angle.get();
    angle.set(withTiming(current + turn(current, -heading - NEEDLE_DEG), { duration: TURN_MS }));
  }, [heading, angle]);
  const needle = useAnimatedStyle(() => ({ transform: [{ rotate: `${angle.get()}deg` }] }));
  return (
    <View
      style={[styles.compass, heading === null && styles.faint]}
      accessible
      accessibilityLabel={
        heading === null ? 'Boussole indisponible' : `Cap ${Math.round(heading)} degrés`
      }
    >
      <Animated.View style={needle}>
        <SymbolView name="safari" size={30} tintColor="#FFFFFF" type="monochrome" />
      </Animated.View>
      {heading !== null && <Text style={styles.heading}>{formatHeading(heading)}</Text>}
    </View>
  );
}

function Chip({ icon, text, color = '#FFFFFF' }: { icon: SFSymbol; text: string; color?: string }) {
  return (
    <View style={styles.chip}>
      <SymbolView name={icon} size={14} tintColor={color} type="monochrome" />
      <Text style={[styles.chipText, { color }]}>{text}</Text>
    </View>
  );
}

/** A monument drawn faintly in the middle of the screen, in the corners of a square: what to aim at. */
function Mark() {
  return (
    <View pointerEvents="none" style={styles.frame}>
      <View style={[styles.corner, styles.topLeft]} />
      <View style={[styles.corner, styles.topRight]} />
      <View style={[styles.corner, styles.bottomLeft]} />
      <View style={[styles.corner, styles.bottomRight]} />
      <SymbolView
        name="building.columns.fill"
        size={MARK_SIZE}
        tintColor="#FFFFFF"
        type="monochrome"
      />
    </View>
  );
}

/**
 * What is written over the camera: the compass, the messages, and the
 * monument aimed at. Few words: icons and figures.
 */
export function CaptureOverlay({ compass, aimed, waiting, message, collected, aimBottom }: Props) {
  // Over the camera, the tabs take the colours of the night.
  useNightTabBar();
  const insets = useSafeAreaInsets();
  const open = useOpenMonument();
  const monument = aimed?.candidate.target.monument;
  return (
    <View pointerEvents="box-none" style={StyleSheet.absoluteFill}>
      <View pointerEvents="box-none" style={[styles.top, { top: insets.top + 8 }]}>
        <Compass reading={compass} />
        {collected !== null && (
          <Chip
            icon="tray.and.arrow.down.fill"
            text={`Collecte · ${collected}`}
            color={NIGHT.gold}
          />
        )}
      </View>
      {message !== null && (
        <Animated.View
          key={message.text}
          entering={FadeInUp}
          exiting={FadeOut}
          pointerEvents="none"
          style={[styles.message, { top: insets.top + 66 }]}
        >
          <SymbolView name={message.icon} size={18} tintColor={NIGHT.gold} type="monochrome" />
          <Text style={styles.messageText}>{message.text}</Text>
        </Animated.View>
      )}
      <Mark />
      <View pointerEvents="box-none" style={[styles.aim, { bottom: aimBottom }]}>
        {waiting === 'photo' ? (
          <Chip icon="hourglass" text="Analyse…" />
        ) : waiting === 'position' ? (
          <Chip icon="location.slash" text="Position…" />
        ) : (
          monument !== undefined &&
          aimed !== null && (
            <Animated.View key={monument.id} entering={FadeIn} style={styles.aimed}>
              <Pressable onPress={() => open(monument.id)} accessibilityRole="button">
                <Text style={styles.name} numberOfLines={2}>
                  {monument.title}
                </Text>
              </Pressable>
              <View style={styles.chips}>
                <Chip
                  icon="ruler"
                  text={
                    aimed.candidate.distanceM === 0
                      ? 'ici'
                      : formatDistance(aimed.candidate.distanceM)
                  }
                />
                {aimed.captured ? (
                  <Chip icon="checkmark.seal.fill" text="Capturé" color={NIGHT.gold} />
                ) : (
                  <Chip
                    icon="star.fill"
                    text={`+${pointsFor(monument.rarityTier)}`}
                    color={NIGHT.gold}
                  />
                )}
              </View>
            </Animated.View>
          )
        )}
      </View>
    </View>
  );
}

// Over a camera, in both appearances of the phone: light on dark veils.
const VEIL = 'rgba(0, 0, 0, 0.5)';
const styles = StyleSheet.create({
  top: {
    position: 'absolute',
    left: 16,
    right: 16,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  // The compass and its heading, in one pill.
  compass: {
    height: 46,
    borderRadius: 23,
    paddingLeft: 8,
    paddingRight: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: VEIL,
  },
  heading: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
  faint: {
    opacity: 0.5,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: 999,
    paddingHorizontal: 11,
    paddingVertical: 6,
    backgroundColor: VEIL,
  },
  chipText: {
    fontSize: 14,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
  message: {
    position: 'absolute',
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 999,
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: 'rgba(22, 24, 27, 0.92)',
  },
  messageText: {
    color: NIGHT.text,
    fontSize: 15,
    fontWeight: '600',
  },
  frame: {
    position: 'absolute',
    top: '50%',
    left: '50%',
    width: FRAME_SIZE,
    height: FRAME_SIZE,
    marginTop: -FRAME_SIZE / 2,
    marginLeft: -FRAME_SIZE / 2,
    alignItems: 'center',
    justifyContent: 'center',
    opacity: 0.22,
  },
  corner: {
    position: 'absolute',
    width: CORNER,
    height: CORNER,
    borderColor: '#FFFFFF',
  },
  topLeft: {
    top: 0,
    left: 0,
    borderTopWidth: LINE,
    borderLeftWidth: LINE,
    borderTopLeftRadius: 12,
  },
  topRight: {
    top: 0,
    right: 0,
    borderTopWidth: LINE,
    borderRightWidth: LINE,
    borderTopRightRadius: 12,
  },
  bottomLeft: {
    bottom: 0,
    left: 0,
    borderBottomWidth: LINE,
    borderLeftWidth: LINE,
    borderBottomLeftRadius: 12,
  },
  bottomRight: {
    bottom: 0,
    right: 0,
    borderBottomWidth: LINE,
    borderRightWidth: LINE,
    borderBottomRightRadius: 12,
  },
  aim: {
    position: 'absolute',
    left: 16,
    right: 16,
    alignItems: 'center',
  },
  aimed: {
    alignItems: 'center',
    gap: 8,
  },
  name: {
    fontFamily: fonts.title,
    fontSize: 21,
    lineHeight: 26,
    color: '#FFFFFF',
    textAlign: 'center',
    textShadowColor: 'rgba(0, 0, 0, 0.7)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 6,
  },
  chips: {
    flexDirection: 'row',
    gap: 8,
  },
});
