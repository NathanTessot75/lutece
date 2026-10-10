import { Stack } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';

import { BUNDLE_MONUMENT_COUNT } from '@/db/bundle';
import { listMonuments } from '@/db/monuments';
import { MonumentList } from '@/features/monuments/MonumentList';
import { type MonumentSection, groupByArrondissement } from '@/features/monuments/sections';
import { formatCount } from '@/lib/format';

export default function ListScreen() {
  const db = useSQLiteContext();
  const [sections, setSections] = useState<MonumentSection[]>([]);

  useEffect(() => {
    let current = true;
    listMonuments(db).then((monuments) => {
      if (current) {
        setSections(groupByArrondissement(monuments));
      }
    });
    return () => {
      current = false;
    };
  }, [db]);

  return (
    <>
      <Stack.Screen options={{ title: 'Lutèce', headerLargeTitle: true }} />
      <MonumentList
        sections={sections}
        caption={`${formatCount(BUNDLE_MONUMENT_COUNT)} monuments protégés à Paris`}
      />
    </>
  );
}
