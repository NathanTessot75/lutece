import { Tabs } from 'expo-router';
import { useMemo, useState } from 'react';

import { TabBar } from '@/features/navigation/TabBar';
import { TabBarHostContext } from '@/lib/tabBar';
import { NIGHT, useTheme } from '@/lib/theme';

export default function TabsLayout() {
  const phone = useTheme();
  // A screen shown at night whatever the appearance asks for its colours.
  const [night, setNight] = useState(false);
  const theme = night ? NIGHT : phone;
  const host = useMemo(() => ({ setNight }), []);
  return (
    <TabBarHostContext value={host}>
      <Tabs
        tabBar={(props) => <TabBar {...props} theme={theme} />}
        screenOptions={{ headerShown: false }}
      >
        <Tabs.Screen name="index" />
        <Tabs.Screen name="collection" />
        <Tabs.Screen name="photo" />
        <Tabs.Screen name="defis" />
        <Tabs.Screen name="profil" />
      </Tabs>
    </TabBarHostContext>
  );
}
