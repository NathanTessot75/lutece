import * as Haptics from 'expo-haptics';
import type { Tabs } from 'expo-router';
import { type SFSymbol, SymbolView } from 'expo-symbols';
import { type ComponentProps, useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';

import { TAB_BAR_HEIGHT, TAB_BAR_SIDE_MARGIN, tabBarBottom } from '@/lib/tabBar';
import { NIGHT, type Theme } from '@/lib/theme';
type TabBarProps = Parameters<NonNullable<ComponentProps<typeof Tabs>['tabBar']>>[0];

type TabLook = {
  /** Not shown: read by VoiceOver. */
  label: string;
  icon: SFSymbol;
  selectedIcon: SFSymbol;
  /** Shown bigger than the others. */
  large?: boolean;
};

/** Each tab, by the name of its route. */
const LOOKS: Record<string, TabLook> = {
  index: { label: 'Carte', icon: 'map', selectedIcon: 'map.fill' },
  collection: { label: 'Collection', icon: 'square.grid.2x2', selectedIcon: 'square.grid.2x2.fill' },
  // The capture, at the heart of the game: always filled.
  photo: {
    label: 'Photo',
    icon: 'building.columns.fill',
    selectedIcon: 'building.columns.fill',
    large: true,
  },
  defis: { label: 'Défis', icon: 'trophy', selectedIcon: 'trophy.fill' },
  profil: { label: 'Profil', icon: 'person', selectedIcon: 'person.fill' },
};

// Between the edge of the pill and the selection.
const INSET = 4;
const ICON_SIZE = 28;
const LARGE_ICON_SIZE = 40;
// How much the selection grows while a finger holds it.
const LIFT_SCALE = 0.16;
// The selection moves like the system's: quick, with a little give.
const MOVE = { damping: 18, stiffness: 240, mass: 0.9 };
// Under a finger, it follows closely.
const FOLLOW = { damping: 30, stiffness: 700 };

function clamp(value: number, low: number, high: number): number {
  'worklet';
  return Math.min(Math.max(value, low), high);
}

/**
 * The tabs in a floating pill, opaque, in the colours of the app. The
 * selection slides from tab to tab; held, it grows and follows the finger,
 * and settles on the tab where the finger leaves it.
 */
export function TabBar({ state, navigation, insets, theme }: TabBarProps & { theme: Theme }) {
  const count = state.routes.length;
  const [width, setWidth] = useState(0);
  const slot = width > 0 ? (width - 2 * INSET) / count : 0;
  // The tab under the finger while one is on the bar.
  const [hovered, setHovered] = useState<number | null>(null);
  const shown = hovered ?? state.index;

  const x = useSharedValue(0);
  const lift = useSharedValue(0);
  const stretch = useSharedValue(0);
  const touching = useSharedValue(false);
  const target = useSharedValue(state.index);

  // The selection goes to the tab shown, stretching on the way like a drop.
  useEffect(() => {
    if (slot === 0 || touching.get()) {
      return;
    }
    x.set(withSpring(state.index * slot, MOVE));
    stretch.set(withSequence(withTiming(1, { duration: 110 }), withSpring(0, MOVE)));
  }, [state.index, slot, x, stretch, touching]);

  const choose = (index: number) => {
    const route = state.routes[index];
    if (route === undefined) {
      return;
    }
    const event = navigation.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
    if (state.index !== index && !event.defaultPrevented) {
      navigation.navigate(route.name, route.params);
    }
  };
  const tick = () => void Haptics.selectionAsync();

  const last = count - 1;
  const pan = Gesture.Pan()
    // A tap does not move: the gesture starts as soon as the finger is down.
    .manualActivation(true)
    .onTouchesDown((_event, manager) => {
      manager.activate();
    })
    .shouldCancelWhenOutside(false)
    .enabled(slot > 0)
    // A quick tap can end before the gesture starts: act on the touch itself.
    .onBegin((event) => {
      touching.set(true);
      lift.set(withSpring(1, MOVE));
      const index = clamp(Math.floor((event.x - INSET) / slot), 0, last);
      if (index !== target.get()) {
        target.set(index);
        scheduleOnRN(tick);
      }
      scheduleOnRN(setHovered, index);
      x.set(withSpring(clamp(event.x - INSET - slot / 2, 0, slot * last), MOVE));
    })
    .onUpdate((event) => {
      x.set(withSpring(clamp(event.x - INSET - slot / 2, 0, slot * last), FOLLOW));
      const index = clamp(Math.floor((event.x - INSET) / slot), 0, last);
      if (index !== target.get()) {
        target.set(index);
        scheduleOnRN(tick);
        scheduleOnRN(setHovered, index);
      }
    })
    .onFinalize((_event, success) => {
      touching.set(false);
      lift.set(withSpring(0, MOVE));
      if (!success) {
        target.set(state.index);
      }
      x.set(withSpring(target.get() * slot, MOVE));
      scheduleOnRN(setHovered, null);
      if (success) {
        scheduleOnRN(choose, target.get());
      }
    });

  // Keep the target on the tab shown once the finger has gone.
  useEffect(() => {
    if (!touching.get()) {
      target.set(state.index);
    }
  }, [state.index, target, touching]);

  const selection = useAnimatedStyle(() => {
    const grow = lift.get() * LIFT_SCALE;
    return {
      transform: [
        { translateX: x.get() },
        { scaleX: 1 + grow + stretch.get() * 0.22 },
        { scaleY: 1 + grow - stretch.get() * 0.1 },
      ],
    };
  });

  return (
    <View
      pointerEvents="box-none"
      style={[
        styles.host,
        {
          bottom: tabBarBottom(insets.bottom),
          left: TAB_BAR_SIDE_MARGIN + insets.left,
          right: TAB_BAR_SIDE_MARGIN + insets.right,
        },
      ]}
    >
      <GestureDetector gesture={pan}>
        <View
          onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
          style={[
            styles.pill,
            {
              backgroundColor: theme.surface,
              borderColor: theme.separator,
              // The night needs a deeper shadow to lift the pill.
              shadowOpacity: theme === NIGHT ? 0.4 : 0.12,
            },
          ]}
          accessibilityRole="tablist"
        >
          {slot > 0 && (
            <Animated.View
              style={[
                styles.selection,
                { width: slot, backgroundColor: theme.separator },
                selection,
              ]}
            />
          )}
          {state.routes.map((route, index) => {
            const look = LOOKS[route.name] ?? {
              label: route.name,
              icon: 'circle',
              selectedIcon: 'circle.fill',
            };
            const color = index === shown ? theme.accent : theme.text;
            return (
              <View
                key={route.key}
                style={styles.item}
                accessible
                accessibilityRole="tab"
                accessibilityLabel={look.label}
                accessibilityState={{ selected: index === state.index }}
                accessibilityActions={[{ name: 'activate' }]}
                onAccessibilityAction={() => choose(index)}
              >
                <SymbolView
                  name={index === shown ? look.selectedIcon : look.icon}
                  size={look.large ? LARGE_ICON_SIZE : ICON_SIZE}
                  tintColor={color}
                  type="monochrome"
                />
              </View>
            );
          })}
        </View>
      </GestureDetector>
    </View>
  );
}

const styles = StyleSheet.create({
  host: {
    position: 'absolute',
  },
  pill: {
    height: TAB_BAR_HEIGHT,
    borderRadius: TAB_BAR_HEIGHT / 2,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: INSET,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 6 },
    shadowRadius: 16,
  },
  selection: {
    position: 'absolute',
    left: INSET,
    top: INSET,
    bottom: INSET,
    borderRadius: (TAB_BAR_HEIGHT - 2 * INSET) / 2,
  },
  item: {
    flex: 1,
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
