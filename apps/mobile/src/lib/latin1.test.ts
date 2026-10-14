import { withLatin1 } from './latin1';

describe('withLatin1', () => {
  // An engine that, like Hermes, only decodes UTF-8.
  class Utf8Only {
    readonly encoding = 'utf-8';
    private readonly inner = new TextDecoder('utf-8');
    constructor(label = 'utf-8') {
      if (!/^utf-?8$/i.test(label)) {
        throw new RangeError(`Unknown encoding: ${label}`);
      }
    }
    decode(input?: ArrayBuffer | ArrayBufferView): string {
      return this.inner.decode(input);
    }
  }
  const Decoder = withLatin1(Utf8Only);

  it('decodes Latin-1, one character per byte', () => {
    const bytes = Uint8Array.from([0x50, 0x61, 0x72, 0x69, 0x73, 0x20, 0xe9, 0xff]);
    expect(new Decoder('latin1').decode(bytes)).toBe('Paris éÿ');
    expect(new Decoder('ISO-8859-1').decode(bytes.subarray(6))).toBe('éÿ');
    expect(new Decoder('latin1').decode()).toBe('');
    const long = new Uint8Array(10000).fill(0x41);
    expect(new Decoder('latin1').decode(long)).toBe('A'.repeat(10000));
  });

  it('leaves the other encodings to the engine', () => {
    const bytes = new TextEncoder().encode('Lutèce');
    expect(new Decoder().decode(bytes)).toBe('Lutèce');
    expect(new Decoder('utf-8').encoding).toBe('utf-8');
    expect(() => new Decoder('utf-16le')).toThrow('Unknown encoding');
  });
});
