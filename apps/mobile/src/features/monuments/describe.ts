import type { MonumentSummary } from '@/db/monuments';
import { formatCentury } from '@/lib/format';

/** One line about a monument: « hôtel · XVIIe siècle ». */
export function describeMonument(monument: MonumentSummary): string {
  const parts = [monument.category, monument.century && formatCentury(monument.century)];
  if (monument.readiness === 'not_ready') {
    parts.push('consultation seule');
  }
  return parts.filter(Boolean).join(' · ');
}
