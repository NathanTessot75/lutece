import { useSQLiteContext } from 'expo-sqlite';
import { SymbolView } from 'expo-symbols';
import { useRef, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import MapView, { type LatLng, Marker, Polygon, type Region } from 'react-native-maps';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { type MonumentPlace, getFootprint } from '@/db/monuments';
import { useCaptures } from '@/features/collection/CapturesProvider';
import { useLocationAccess } from '@/lib/location';
import { useTabBarRoom } from '@/lib/tabBar';
import { type Theme, useTheme } from '@/lib/theme';
import { Text } from '@/lib/typography';

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
// The map is on the player while its centre is this close to them, in shares of its span.
const ON_POSITION_SHARE = 0.1;
const PLACE_SIZE = 32;
const SELECTED_PLACE_SIZE = 42;
const POSITION_BUTTON_SIZE = 48;

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

/** Whether the map is centred on the player. */
function isOnPosition(shown: Region, player: LatLng | null): boolean {
  return (
    player !== null &&
    Math.abs(shown.latitude - player.latitude) < shown.latitudeDelta * ON_POSITION_SHARE &&
    Math.abs(shown.longitude - player.longitude) < shown.longitudeDelta * ON_POSITION_SHARE
  );
}

/** The captured places stand out in colour (SPEC §2): slate to capture, verdigris once captured. */
function placeColor(monument: MonumentPlace, captured: boolean, theme: Theme): string {
  if (captured) {
    return theme.mapCaptured;
  }
  return monument.readiness === 'not_ready' ? theme.muted : theme.mapToCapture;
}

/**
 * The colour of a group: slate while some of its places remain to capture,
 * verdigris once all are captured.
 */
function groupColor(
  capturableIds: string[],
  captured: { has: (id: string) => boolean },
  theme: Theme,
): string {
  if (capturableIds.length === 0) {
    return theme.muted;
  }
  return capturableIds.every((id) => captured.has(id)) ? theme.mapCaptured : theme.mapToCapture;
}

/** A place on the map: a round badge with a monument in it. */
function Place({ color, selected, theme }: { color: string; selected: boolean; theme: Theme }) {
  const size = selected ? SELECTED_PLACE_SIZE : PLACE_SIZE;
  return (
    <View
      style={[
        styles.place,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          borderWidth: selected ? 3 : 2,
          backgroundColor: color,
          borderColor: theme.onMap,
        },
      ]}
    >
      <SymbolView
        name="building.columns.fill"
        size={size * 0.52}
        tintColor={theme.onMap}
        type="monochrome"
        // The pointed roof makes the symbol look low: a little higher looks centred.
        style={{ transform: [{ translateY: -size * 0.03 }] }}
      />
    </View>
  );
}

function groupSize(count: number): number {
  if (count < 10) {
    return 34;
  }
  return count < 100 ? 40 : 48;
}

function Group({ count, color, theme }: { count: number; color: string; theme: Theme }) {
  const size = groupSize(count);
  return (
    <View
      style={[
        styles.group,
        { width: size, height: size, borderRadius: size / 2, backgroundColor: color },
        { borderColor: theme.onMap },
      ]}
    >
      <Text style={[styles.groupCount, { color: theme.onMap }]}>{count}</Text>
    </View>
  );
}

export function MonumentMap() {
  const db = useSQLiteContext();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  // The floating tabs cover the bottom of the map.
  const tabBarRoom = useTabBarRoom();
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
  const [onPosition, setOnPosition] = useState(false);
  const [cardHeight, setCardHeight] = useState(0);

  const showRegion = (shown: Region) => {
    region.current = shown;
    setOnPosition(isOnPosition(shown, position.current));
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
    setOnPosition(isOnPosition(region.current, found));
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
        mapPadding={{
          top: 0,
          right: 0,
          bottom: tabBarRoom + (selection ? cardHeight + CARD_GAP : 0),
          left: 0,
        }}
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
        {marks.map((mark) => {
          if (mark.kind === 'group') {
            const color = groupColor(mark.capturableIds, captured, theme);
            return (
              <Marker
                // A group is drawn once: its colours only change with a new key.
                key={`${mark.key}:${color}:${theme.onMap}`}
                coordinate={{ latitude: mark.latitude, longitude: mark.longitude }}
                tracksViewChanges={false}
                onPress={() => zoomInto(mark)}
              >
                <Group count={mark.count} color={color} theme={theme} />
              </Marker>
            );
          }
          return (
            <Marker
              key={mark.monument.id}
              coordinate={{ latitude: mark.monument.lat, longitude: mark.monument.lon }}
              centerOffset={{ x: 0, y: 0 }}
              anchor={{ x: 0.5, y: 0.5 }}
              onSelect={() => select(mark.monument)}
              onDeselect={() => deselect(mark.monument)}
            >
              <Place
                color={placeColor(mark.monument, captured.has(mark.monument.id), theme)}
                selected={selection?.monument.id === mark.monument.id}
                theme={theme}
              />
            </Marker>
          );
        })}
      </MapView>
      <View
        style={[styles.overlay, { bottom: insets.bottom + Math.max(tabBarRoom, CARD_GAP) }]}
        pointerEvents="box-none"
      >
        <View style={styles.buttons}>
          {(located || !location.granted) && (
            <Pressable
              style={[styles.button, { backgroundColor: theme.surface }]}
              onPress={showPosition}
              accessibilityRole="button"
              accessibilityLabel={location.granted ? 'Ma position' : 'Activer ma position'}
            >
              <SymbolView
                // Like in Plans: filled while the map is on the player.
                name={!location.granted ? 'location.slash' : onPosition ? 'location.fill' : 'location'}
                size={22}
                tintColor={theme.accent}
                type="monochrome"
              />
            </Pressable>
          )}
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
  place: {
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000000',
    shadowOpacity: 0.25,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
  },
  group: {
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    shadowColor: '#000000',
    shadowOpacity: 0.2,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
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
    width: POSITION_BUTTON_SIZE,
    height: POSITION_BUTTON_SIZE,
    borderRadius: POSITION_BUTTON_SIZE / 2,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000000',
    shadowOpacity: 0.18,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
  },
});
