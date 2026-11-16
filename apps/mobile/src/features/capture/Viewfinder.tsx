import { CameraView, useCameraPermissions } from 'expo-camera';
import { type Ref, useImperativeHandle, useRef, useState } from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

export type ViewfinderHandle = {
  /** Take a picture and give where the camera wrote it; nothing without a camera. */
  takePicture: () => Promise<string | null>;
};

type Props = {
  ref: Ref<ViewfinderHandle>;
  /** Whether the screen is in front: the camera rests otherwise. */
  active: boolean;
};

const PICTURE_QUALITY = 0.8;
// A camera that does not answer must not hold a capture back.
const PICTURE_TIMEOUT_MS = 4000;

function giveUp(): Promise<null> {
  return new Promise((resolve) => setTimeout(() => resolve(null), PICTURE_TIMEOUT_MS));
}

/**
 * What the camera sees, over the whole screen. Without a camera, a capture
 * goes without a picture.
 */
export function Viewfinder({ ref, active }: Props) {
  const [permission, request] = useCameraPermissions({ request: true });
  const camera = useRef<CameraView>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const allowed = permission?.granted ?? false;

  useImperativeHandle(ref, () => ({
    takePicture: async () => {
      if (!allowed || !ready || failed) {
        return null;
      }
      try {
        const taking = camera.current?.takePictureAsync({ quality: PICTURE_QUALITY });
        const picture = await Promise.race([taking, giveUp()]);
        return picture?.uri ?? null;
      } catch {
        return null;
      }
    },
  }));

  const allow = () => {
    if (permission?.canAskAgain === false) {
      void Linking.openSettings();
    } else {
      void request();
    }
  };

  return (
    <View style={styles.frame}>
      {allowed && !failed ? (
        <CameraView
          ref={camera}
          style={StyleSheet.absoluteFill}
          facing="back"
          active={active}
          onCameraReady={() => setReady(true)}
          onMountError={() => setFailed(true)}
        />
      ) : (
        <View style={styles.missing}>
          <Text style={styles.missingText}>
            {failed
              ? 'Caméra indisponible : la capture se fera sans photo.'
              : 'Sans la caméra, la capture se fera sans photo.'}
          </Text>
          {!failed && permission !== null && (
            <Pressable style={styles.allow} onPress={allow} accessibilityRole="button">
              <Text style={styles.allowLabel}>Autoriser la caméra</Text>
            </Pressable>
          )}
        </View>
      )}
    </View>
  );
}

// The viewfinder is dark in both appearances of the phone, like a camera.
const styles = StyleSheet.create({
  frame: {
    ...StyleSheet.absoluteFill,
    backgroundColor: '#000000',
  },
  // Above the monument drawn faintly in the middle of the screen.
  missing: {
    position: 'absolute',
    top: '24%',
    left: 0,
    right: 0,
    alignItems: 'center',
    gap: 14,
    paddingHorizontal: 32,
  },
  missingText: {
    color: '#C7C7CC',
    fontSize: 15,
    textAlign: 'center',
  },
  allow: {
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 9,
    backgroundColor: '#FFFFFF',
  },
  allowLabel: {
    color: '#1C1C1E',
    fontSize: 15,
    fontWeight: '600',
  },
});
