import { useRouter } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import MapView, { type LatLng, Marker, Polygon, type Region } from 'react-native-maps';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { type MonumentPlace, getFootprint } from '@/db/monuments';
import { useCaptures } from '@/features/collection/CapturesProvider';
import { useLocationAccess } from '@/lib/location';
import { type Theme, useTheme } from '@/lib/theme';

import { type Outline, parseFootprint } from './footprint';
import { NEIGHBOURHOOD_SPAN, PARIS, isInParis } from './grid';
import { type Mark, loadMarks } from './marks';
import { SelectedMonumentCard } from './SelectedMonumentCard';

// How much closer the map gets when a group is touched.
const GROUP_ZOOM = 3;
const MOVE_DURATION_MS = 350;
const POSITION_COLOR = '#007AFF';
// The space left under and above the card of the selected monument.
const CARD_GAP = 12;
// The fill of an outline lets the map show through.
const OUTLINE_FILL_OPACITY = '33';

type Selection = {
  monument: MonumentPlace;
  outlines: Outline[];
};

function around({ latitude, longitude }: LatLng): Region {
  return {
    latitude,
    longitude,
    latitudeDelta: NEIGHBOURHOOD_SPAN,
    longitudeDelta: NEIGHBOURHOOD_SPAN,
  };
}

function hasPin(marks: Mark[], monument: MonumentPlace): boolean {
  return marks.some((mark) => mark.kind === 'monument' && mark.monument.id === monument.id);
}

/** The city takes colour as it is captured: grey until then (SPEC §2). */
function pinColor(monument: MonumentPlace, captured: boolean, theme: Theme): string {
  if (captured) {
    return theme.accent;
  }
  return monument.readiness === 'not_ready' ? theme.muted : theme.pending;
}

function groupSize(count: number): number {
  if (count < 10) {
    return 34;
  }
  return count < 100 ? 40 : 48;
}

function Group({ count, theme }: { count: number; theme: Theme }) {
  const size = groupSize(count);
  return (
    <View
      style={[
        styles.group,
        { width: size, height: size, borderRadius: size / 2, backgroundColor: theme.pending },
        { borderColor: theme.background },
      ]}
    >
      <Text style={[styles.groupCount, { color: theme.background }]}>{count}</Text>
    </View>
  );
}

export function MonumentMap() {
  const db = useSQLiteContext();
  const router = useRouter();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const { byMonument: captured } = useCaptures();
  const location = useLocationAccess();
  const map = useRef<MapView>(null);
  const region = useRef(PARIS);
  const latestLoad = useRef(0);
  const position = useRef<LatLng | null>(null);
  // The map moves to the player by itself once, as soon as it is ready and
  // knows where they are, unless they have touched it before.
  const ready = useRef(false);
  const touched = useRef(false);
  const centred = useRef(false);
  const [marks, setMarks] = useState<Mark[]>([]);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [located, setLocated] = useState(false);
  const [cardHeight, setCardHeight] = useState(0);

  const showRegion = (shown: Region) => {
    region.current = shown;
    const load = ++latestLoad.current;
    void loadMarks(db, shown).then((loaded) => {
      if (load === latestLoad.current) {
        setMarks(loaded);
        // A monument that no longer has its own pin is no longer selected.
        setSelection((current) => (current && hasPin(loaded, current.monument) ? current : null));
      }
    });
  };

  const select = (monument: MonumentPlace) => {
    setSelection({ monument, outlines: [] });
    void getFootprint(db, monument.id).then((footprint) => {
      if (footprint !== null) {
        const outlines = parseFootprint(footprint);
        setSelection((current) =>
          current?.monument.id === monument.id ? { monument, outlines } : current,
        );
      }
    });
  };

  const deselect = (monument: MonumentPlace) => {
    setSelection((current) => (current?.monument.id === monument.id ? null : current));
  };

  const zoomInto = ({ latitude, longitude }: LatLng) => {
    map.current?.animateToRegion(
      {
        latitude,
        longitude,
        latitudeDelta: region.current.latitudeDelta / GROUP_ZOOM,
        longitudeDelta: region.current.longitudeDelta / GROUP_ZOOM,
      },
      MOVE_DURATION_MS,
    );
  };

  const centreOnce = () => {
    const found = position.current;
    if (!ready.current || found === null || centred.current) {
      return;
    }
    centred.current = true;
    if (!touched.current && isInParis(found.latitude, found.longitude)) {
      map.current?.animateToRegion(around(found), MOVE_DURATION_MS);
    }
  };

  const locate = (found: LatLng) => {
    if (position.current === null) {
      setLocated(true);
    }
    position.current = found;
    centreOnce();
  };

  const showPosition = () => {
    if (!location.granted) {
      location.ask();
    } else if (position.current !== null) {
      map.current?.animateToRegion(around(position.current), MOVE_DURATION_MS);
    }
  };

  return (
    <View style={styles.screen}>
      <MapView
        ref={map}
        style={styles.screen}
        initialRegion={PARIS}
        showsUserLocation={location.granted}
        // The dot of the player keeps the blue of iOS, whatever tints the app.
        tintColor={POSITION_COLOR}
        pitchEnabled={false}
        // The credits of the map stay readable above the card of a monument.
        mapPadding={{ top: 0, right: 0, bottom: selection ? cardHeight + CARD_GAP : 0, left: 0 }}
        onMapReady={() => {
          ready.current = true;
          centreOnce();
        }}
        onTouchStart={() => {
          touched.current = true;
        }}
        onRegionChangeComplete={showRegion}
        onUserLocationChange={({ nativeEvent }) => {
          if (nativeEvent.coordinate) {
            locate(nativeEvent.coordinate);
          }
        }}
      >
        {selection?.outlines.map((outline, index) => (
          <Polygon
            key={`${selection.monument.id}:${index}`}
            coordinates={outline.coordinates}
            holes={outline.holes}
            strokeColor={theme.accent}
            strokeWidth={2}
            fillColor={`${theme.accent}${OUTLINE_FILL_OPACITY}`}
          />
        ))}
        {marks.map((mark) =>
          mark.kind === 'group' ? (
            <Marker
              // A group is drawn once: its colours only change with a new key.
              key={`${mark.key}:${theme.pending}`}
              coordinate={{ latitude: mark.latitude, longitude: mark.longitude }}
              tracksViewChanges={false}
              onPress={() => zoomInto(mark)}
            >
              <Group count={mark.count} theme={theme} />
            </Marker>
          ) : (
            <Marker
              key={mark.monument.id}
              coordinate={{ latitude: mark.monument.lat, longitude: mark.monument.lon }}
              pinColor={pinColor(mark.monument, captured.has(mark.monument.id), theme)}
              onSelect={() => select(mark.monument)}
              onDeselect={() => deselect(mark.monument)}
            />
          ),
        )}
      </MapView>
      <View style={[styles.overlay, { bottom: insets.bottom + CARD_GAP }]} pointerEvents="box-none">
        <View style={styles.buttons}>
          {(located || !location.granted) && (
            <Pressable
              style={[styles.button, { backgroundColor: theme.surface }]}
              onPress={showPosition}
              accessibilityRole="button"
            >
              <Text style={[styles.buttonLabel, { color: theme.accent }]}>
                {location.granted ? 'Ma position' : 'Activer ma position'}
              </Text>
            </Pressable>
          )}
          <Pressable
            style={[styles.button, { backgroundColor: theme.accent }]}
            onPress={() => router.push('/capture')}
            accessibilityRole="button"
          >
            <Text style={[styles.buttonLabel, { color: theme.onAccent }]}>Capturer</Text>
          </Pressable>
        </View>
        {selection && (
          <View onLayout={({ nativeEvent }) => setCardHeight(nativeEvent.layout.height)}>
            <SelectedMonumentCard monument={selection.monument} />
          </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  group: {
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
  },
  groupCount: {
    fontSize: 14,
    fontWeight: '700',
  },
  overlay: {
    position: 'absolute',
    left: 16,
    right: 16,
    gap: 10,
  },
  buttons: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
  },
  button: {
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 9,
    shadowColor: '#000000',
    shadowOpacity: 0.18,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
  },
  buttonLabel: {
    fontSize: 15,
    fontWeight: '600',
  },
});
