import {
  capitalize,
  formatArrondissement,
  formatCentury,
  formatCount,
  formatDate,
  formatDistance,
  formatHeading,
} from './format';

describe('formats', () => {
  it('writes centuries in Roman numerals', () => {
    expect(formatCentury(17)).toBe('XVIIe siècle');
    expect(formatCentury(1)).toBe('Ier siècle');
    expect(formatCentury(19)).toBe('XIXe siècle');
  });

  it('writes arrondissements the French way', () => {
    expect(formatArrondissement(1)).toBe('1er arrondissement');
    expect(formatArrondissement(18)).toBe('18e arrondissement');
  });

  it('groups thousands with a space that does not break', () => {
    expect(formatCount(1878)).toBe('1 878');
    expect(formatCount(42)).toBe('42');
  });

  it('rounds distances to what a GPS can tell', () => {
    expect(formatDistance(42.3)).toBe('42 m');
    expect(formatDistance(268)).toBe('270 m');
    expect(formatDistance(1234)).toBe('1 230 m');
  });

  it('names the direction of a heading', () => {
    expect(formatHeading(0)).toBe('0° nord');
    expect(formatHeading(110)).toBe('110° est');
    expect(formatHeading(135)).toBe('135° sud-est');
    expect(formatHeading(359.6)).toBe('0° nord');
    expect(formatHeading(340)).toBe('340° nord');
  });

  it('writes dates in full', () => {
    // Midday in UTC is the same day on any clock of Europe.
    expect(formatDate('2026-10-11T12:22:57.715Z')).toBe('11 octobre 2026');
    expect(formatDate('2027-05-01T12:00:00.000Z')).toBe('1er mai 2027');
    expect(formatDate('2027-08-31T12:00:00.000Z')).toBe('31 août 2027');
  });

  it('capitalises a word, accents included', () => {
    expect(capitalize('hôtel')).toBe('Hôtel');
    expect(capitalize('église')).toBe('Église');
  });
});
