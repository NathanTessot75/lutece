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
  /** What is aimed at, written over the image. */
  label: string;
};

const PICTURE_QUALITY = 0.8;
// A camera that does not answer must not hold a capture back.
const PICTURE_TIMEOUT_MS = 4000;

function giveUp(): Promise<null> {
  return new Promise((resolve) => setTimeout(() => resolve(null), PICTURE_TIMEOUT_MS));
}

/** What the camera sees. Without a camera, a capture goes without a picture. */
export function Viewfinder({ ref, active, label }: Props) {
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
      <View style={styles.caption}>
        <Text style={styles.captionText} numberOfLines={2}>
          {label}
        </Text>
      </View>
    </View>
  );
}

// The viewfinder is dark in both appearances of the phone, like a camera.
const styles = StyleSheet.create({
  frame: {
    aspectRatio: 1,
    backgroundColor: '#000000',
    justifyContent: 'flex-end',
  },
  missing: {
    ...StyleSheet.absoluteFill,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 14,
    padding: 32,
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
  caption: {
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: 44,
    backgroundColor: 'rgba(0, 0, 0, 0.45)',
  },
  captionText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '600',
    textAlign: 'center',
  },
});
