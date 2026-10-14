import { SIDE, centreSquare, referencePhotoUrl, toPixels } from './pixels';

function plain(colour: [number, number, number], channels = 4): Uint8Array {
  const data = new Uint8Array(SIDE * SIDE * channels);
  for (let index = 0; index < SIDE * SIDE; index++) {
    data.set(colour, index * channels);
    if (channels === 4) {
      data[index * channels + 3] = 255;
    }
  }
  return data;
}

describe('toPixels', () => {
  it('scales the colours as the pipeline does', () => {
    // pipeline/tests/test_vision.py: the same values for white and black.
    const white = toPixels(plain([255, 255, 255]), 4);
    expect(white).toHaveLength(3 * SIDE * SIDE);
    const plane = SIDE * SIDE;
    expect(white[0]).toBeCloseTo(2.249, 3);
    expect(white[plane]).toBeCloseTo(2.429, 3);
    expect(white[2 * plane + 100]).toBeCloseTo(2.64, 3);
    const black = toPixels(plain([0, 0, 0], 3), 3);
    expect(black[10]).toBeCloseTo(-2.118, 3);
    expect(black[plane + 10]).toBeCloseTo(-2.036, 3);
    expect(black[2 * plane + 10]).toBeCloseTo(-1.804, 3);
  });

  it('puts the red, green and blue of each pixel in three planes', () => {
    const red = toPixels(plain([255, 0, 0]), 4);
    const plane = SIDE * SIDE;
    expect(red[5]).toBeGreaterThan(0);
    expect(red[plane + 5]).toBeLessThan(0);
    expect(red[2 * plane + 5]).toBeLessThan(0);
  });

  it('reads photos on 16 bits', () => {
    const data = new Uint16Array(SIDE * SIDE * 3).fill(65535);
    expect(toPixels(data, 3, 16)[0]).toBeCloseTo(2.249, 3);
  });
});

describe('centreSquare', () => {
  it('keeps the centre of a photo, as the pipeline crops it', () => {
    expect(centreSquare(500, 375)).toEqual({ originX: 62, originY: 0, width: 375, height: 375 });
    expect(centreSquare(375, 500)).toEqual({ originX: 0, originY: 62, width: 375, height: 375 });
    expect(centreSquare(300, 300)).toEqual({ originX: 0, originY: 0, width: 300, height: 300 });
  });
});

describe('referencePhotoUrl', () => {
  it('asks for the width at which the pipeline read the photo', () => {
    const thumbs = 'https://thumb.wikimedia.org/wikipedia/commons/thumb';
    expect(referencePhotoUrl(`${thumbs}/9/95/Tour.jpg/960px-Tour.jpg?utm_source=x`)).toBe(
      `${thumbs}/9/95/Tour.jpg/500px-Tour.jpg?utm_source=x`,
    );
    const original = 'https://upload.wikimedia.org/wikipedia/commons/7/7a/Petite.jpg';
    expect(referencePhotoUrl(original)).toBe(original);
  });
});
