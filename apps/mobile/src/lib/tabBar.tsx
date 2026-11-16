import { useFocusEffect } from 'expo-router';
import { createContext, useCallback, useContext } from 'react';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

/** The height of the floating pill of the tabs. */
export const TAB_BAR_HEIGHT = 62;
/** Between the pill and the edges of the screen. */
export const TAB_BAR_SIDE_MARGIN = 21;
// Between the pill and what scrolls above it, at the end of a list.
const TAB_BAR_GAP = 12;

/** Between the pill and the bottom of the screen: low, like the system's. */
export function tabBarBottom(safeBottom: number): number {
  return Math.max(safeBottom - 14, 12);
}

/** What the tabs give to their screens. */
type TabBarHost = {
  /** Ask for a tab bar in the colours of the night. */
  setNight: (night: boolean) => void;
};

/** The tabs give their screens a host; screens outside the tabs have none. */
export const TabBarHostContext = createContext<TabBarHost | null>(null);

/**
 * Gives the tab bar the colours of the night while the calling screen is
 * shown: on a dark screen, the tint of the light appearance cannot be seen.
 */
export function useNightTabBar(): void {
  const host = useContext(TabBarHostContext);
  useFocusEffect(
    useCallback(() => {
      host?.setNight(true);
      return () => host?.setNight(false);
    }, [host]),
  );
}

/**
 * How much the floating tab bar covers above the bottom safe area: the room
 * to leave under the content of a screen of the tabs. None outside the tabs.
 */
export function useTabBarRoom(): number {
  const host = useContext(TabBarHostContext);
  const { bottom } = useSafeAreaInsets();
  if (host === null) {
    return 0;
  }
  return tabBarBottom(bottom) + TAB_BAR_HEIGHT + TAB_BAR_GAP - bottom;
}

/**
 * For a scroll view that adjusts to the safe area by itself
 * (`contentInsetAdjustmentBehavior="automatic"`): its end clears the tab bar.
 */
export function useTabBarInsets(): {
  contentInset: { bottom: number };
  scrollIndicatorInsets: { bottom: number };
} {
  const room = useTabBarRoom();
  return { contentInset: { bottom: room }, scrollIndicatorInsets: { bottom: room } };
}
