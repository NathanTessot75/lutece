// Hermes decodes text from UTF-8 only. fast-png creates a Latin-1 decoder as
// it loads, for the text notes a PNG may carry: without one, the import fails.
// Latin-1 is simple enough to decode here: each byte is the character of the
// same code. Import this module before fast-png.

const LATIN1 = /^(latin1|iso-8859-1|iso8859-1|l1|ascii|us-ascii|windows-1252)$/i;

type Decoder = { readonly encoding: string; decode(input?: ArrayBuffer | ArrayBufferView): string };
type DecoderClass = new (label?: string, options?: { fatal?: boolean }) => Decoder;

class Latin1Decoder implements Decoder {
  readonly encoding = 'windows-1252';

  decode(input?: ArrayBuffer | ArrayBufferView): string {
    if (input === undefined) {
      return '';
    }
    const bytes = ArrayBuffer.isView(input)
      ? new Uint8Array(input.buffer, input.byteOffset, input.byteLength)
      : new Uint8Array(input);
    let text = '';
    // In slices: a call takes a limited number of arguments.
    for (let start = 0; start < bytes.length; start += 4096) {
      text += String.fromCharCode(...bytes.subarray(start, start + 4096));
    }
    return text;
  }
}

/** A text decoder that also knows Latin-1, built on the one the engine gives. */
export function withLatin1(Native: DecoderClass): DecoderClass {
  return class TextDecoder {
    constructor(label = 'utf-8', options?: { fatal?: boolean }) {
      return (LATIN1.test(label.trim()) ? new Latin1Decoder() : new Native(label, options)) as TextDecoder;
    }
  } as unknown as DecoderClass;
}

function knowsLatin1(Native: DecoderClass): boolean {
  try {
    new Native('latin1');
    return true;
  } catch {
    return false;
  }
}

const scope = globalThis as unknown as { TextDecoder: DecoderClass };
if (!knowsLatin1(scope.TextDecoder)) {
  scope.TextDecoder = withLatin1(scope.TextDecoder);
}
