import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';

import { type Groups, loadGroups } from '@/db/series';

/** The series and arrondissements of the bundle, with their places; none while loading. */
export function useGroups(): Groups | null {
  const db = useSQLiteContext();
  const [groups, setGroups] = useState<Groups | null>(null);
  useEffect(() => {
    let current = true;
    void loadGroups(db).then((found) => {
      if (current) {
        setGroups(found);
      }
    });
    return () => {
      current = false;
    };
  }, [db]);
  return groups;
}
