import { useRouter } from 'expo-router';

/** Open the page of a monument over the screen that shows it. */
export function useOpenMonument(): (id: string) => void {
  const router = useRouter();
  return (id) => router.push({ pathname: '/monument/[id]', params: { id } });
}
