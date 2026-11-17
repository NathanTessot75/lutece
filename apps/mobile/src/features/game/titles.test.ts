import { TITLES, titleFor } from './titles';

describe('titleFor', () => {
  it('starts every player as a Badaud', () => {
    expect(titleFor(0)).toEqual({ title: TITLES[0], next: TITLES[1], progress: 0 });
  });

  it('gives a title from its first point on', () => {
    expect(titleFor(99).title.name).toBe('Badaud');
    expect(titleFor(100).title.name).toBe('Promeneur');
    expect(titleFor(10_000).title.name).toBe('Gardien de Lutèce');
  });

  it('measures the way to the next title', () => {
    const standing = titleFor(550);
    expect(standing.title.name).toBe('Flâneur');
    expect(standing.next?.name).toBe('Arpenteur');
    expect(standing.progress).toBe(0.5);
  });

  it('has nothing after the last title', () => {
    expect(titleFor(25_000)).toEqual({ title: TITLES[7], next: null, progress: 1 });
  });

  it('climbs in order', () => {
    const steps = TITLES.map((title) => title.from);
    expect(steps).toEqual([...steps].sort((a, b) => a - b));
  });
});
