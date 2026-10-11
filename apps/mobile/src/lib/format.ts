const ROMAN: readonly (readonly [number, string])[] = [
  [10, 'X'],
  [9, 'IX'],
  [5, 'V'],
  [4, 'IV'],
  [1, 'I'],
];

function toRoman(value: number): string {
  let rest = value;
  let written = '';
  for (const [amount, letters] of ROMAN) {
    while (rest >= amount) {
      written += letters;
      rest -= amount;
    }
  }
  return written;
}

/** 17 → « XVIIe siècle », 1 → « Ier siècle ». */
export function formatCentury(century: number): string {
  return `${toRoman(century)}${century === 1 ? 'er' : 'e'} siècle`;
}

/** 1 → « 1er arrondissement », 4 → « 4e arrondissement ». */
export function formatArrondissement(arrondissement: number): string {
  return `${arrondissement}${arrondissement === 1 ? 'er' : 'e'} arrondissement`;
}

/** 1878 → « 1 878 », with a space that never breaks the number over two lines. */
export function formatCount(count: number): string {
  return count.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0');
}

/** « hôtel » → « Hôtel ». */
export function capitalize(text: string): string {
  return text.charAt(0).toLocaleUpperCase('fr') + text.slice(1);
}

/** 42.3 → « 42 m », 268 → « 270 m ». */
export function formatDistance(metres: number): string {
  const rounded = metres < 100 ? Math.round(metres) : Math.round(metres / 10) * 10;
  return `${formatCount(rounded)}\u00a0m`;
}

const DIRECTIONS = ['nord', 'nord-est', 'est', 'sud-est', 'sud', 'sud-ouest', 'ouest', 'nord-ouest'];

/** 135 → « 135° sud-est ». */
export function formatHeading(degrees: number): string {
  const rounded = Math.round(degrees) % 360;
  return `${rounded}° ${DIRECTIONS[Math.round(rounded / 45) % DIRECTIONS.length]}`;
}

const MONTHS = [
  'janvier',
  'février',
  'mars',
  'avril',
  'mai',
  'juin',
  'juillet',
  'août',
  'septembre',
  'octobre',
  'novembre',
  'décembre',
];

/** An ISO date → « 11 octobre 2026 », « 1er mai 2027 », on the clock of the phone. */
export function formatDate(iso: string): string {
  const date = new Date(iso);
  const day = date.getDate();
  return `${day}${day === 1 ? 'er' : ''} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}
