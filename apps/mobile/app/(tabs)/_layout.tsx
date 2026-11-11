import { NativeTabs } from 'expo-router/unstable-native-tabs';

import { useTheme } from '@/lib/theme';
import { fonts } from '@/lib/typography';

export default function TabsLayout() {
  const theme = useTheme();
  return (
    <NativeTabs tintColor={theme.accent} labelStyle={{ fontFamily: fonts.medium }}>
      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Icon sf={{ default: 'map', selected: 'map.fill' }} />
        <NativeTabs.Trigger.Label>Carte</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="collection">
        <NativeTabs.Trigger.Icon sf={{ default: 'book', selected: 'book.fill' }} />
        <NativeTabs.Trigger.Label>Collection</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="photo">
        <NativeTabs.Trigger.Icon sf={{ default: 'camera', selected: 'camera.fill' }} />
        <NativeTabs.Trigger.Label>Photo</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="defis">
        <NativeTabs.Trigger.Icon sf={{ default: 'trophy', selected: 'trophy.fill' }} />
        <NativeTabs.Trigger.Label>Défis</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="profil">
        <NativeTabs.Trigger.Icon sf={{ default: 'person', selected: 'person.fill' }} />
        <NativeTabs.Trigger.Label>Profil</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
