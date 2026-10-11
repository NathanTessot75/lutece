import * as Location from 'expo-location';
import { useEffect, useRef, useState } from 'react';
import { Linking } from 'react-native';

export type LocationAccess = {
  /** Whether the app may read the position while it is in use. */
  granted: boolean;
  /** Ask for it again, or open the settings once iOS no longer lets the app ask. */
  ask: () => void;
};

/**
 * Ask for the position when a screen opens. The app only reads it while it is
 * in use: it never asks to follow the phone in the background.
 */
export function useLocationAccess(): LocationAccess {
  const [permission, request] = Location.useForegroundPermissions({ request: true });
  const ask = () => {
    if (permission?.canAskAgain === false) {
      void Linking.openSettings();
    } else {
      void request();
    }
  };
  return { granted: permission?.granted ?? false, ask };
}

/** Where the phone is, and within how many metres. */
export type Position = {
  latitude: number;
  longitude: number;
  accuracyM: number;
};

/** Where the top of the phone points, and how well the compass is calibrated. */
export type CompassReading = {
  /** Degrees clockwise from true north. */
  headingDeg: number;
  /** From 3, within 20°, down to 0, which is lost. */
  level: number;
};

// A reading that differs by less than this does not redraw the screen.
const HEADING_STEP_DEG = 2;

/** Follow the position as precisely as the phone can, while `enabled`. */
export function usePosition(enabled: boolean): Position | null {
  const [position, setPosition] = useState<Position | null>(null);
  useEffect(() => {
    if (!enabled) {
      return;
    }
    let stopped = false;
    let subscription: Location.LocationSubscription | undefined;
    void Location.watchPositionAsync(
      { accuracy: Location.Accuracy.Highest, distanceInterval: 1 },
      ({ coords }) =>
        setPosition({
          latitude: coords.latitude,
          longitude: coords.longitude,
          accuracyM: coords.accuracy ?? Infinity,
        }),
    ).then((started) => {
      if (stopped) {
        started.remove();
      } else {
        subscription = started;
      }
    });
    return () => {
      stopped = true;
      subscription?.remove();
    };
  }, [enabled]);
  return enabled ? position : null;
}

/** Follow the compass while `enabled`; nothing on a device that has none. */
export function useCompass(enabled: boolean): CompassReading | null {
  const [reading, setReading] = useState<CompassReading | null>(null);
  const shown = useRef<CompassReading | null>(null);
  useEffect(() => {
    if (!enabled) {
      return;
    }
    let stopped = false;
    let subscription: Location.LocationSubscription | undefined;
    void Location.watchHeadingAsync(({ trueHeading, magHeading, accuracy }) => {
      // The true heading is -1 until the phone knows where it is.
      const next = { headingDeg: trueHeading >= 0 ? trueHeading : magHeading, level: accuracy };
      const last = shown.current;
      const moved =
        last === null ||
        last.level !== next.level ||
        Math.abs(((next.headingDeg - last.headingDeg + 540) % 360) - 180) >= HEADING_STEP_DEG;
      if (moved) {
        shown.current = next;
        setReading(next);
      }
    }).then((started) => {
      if (stopped) {
        started.remove();
      } else {
        subscription = started;
      }
    });
    return () => {
      stopped = true;
      subscription?.remove();
    };
  }, [enabled]);
  return enabled ? reading : null;
}
