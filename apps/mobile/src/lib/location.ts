import * as Location from 'expo-location';
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
