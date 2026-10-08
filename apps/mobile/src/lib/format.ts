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
