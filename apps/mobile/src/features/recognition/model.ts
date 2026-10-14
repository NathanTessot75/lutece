import { Asset } from 'expo-asset';
import { InferenceSession, Tensor } from 'onnxruntime-react-native';

import { SIDE } from './pixels';

// DINOv2 ViT-S/14 with its weights on 8 bits, exported by the pipeline
// (export_model) and copied with the vectors of the reference photos.
// Metro hands the model over as an asset (metro.config.js), an extension the
// lint rule does not know.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const MODEL_ASSET: number = require('../../../assets/models/dinov2-small-int8.onnx');

let opening: Promise<InferenceSession> | null = null;

/** Load the model once: the first time takes a moment, the others nothing. */
export function openModel(): Promise<InferenceSession> {
  opening ??= (async () => {
    const asset = Asset.fromModule(MODEL_ASSET);
    await asset.downloadAsync();
    if (!asset.localUri) {
      throw new Error('The image model is not on the phone');
    }
    return InferenceSession.create(asset.localUri.replace(/^file:\/\//, ''));
  })();
  opening.catch(() => {
    // A failed load may be tried again.
    opening = null;
  });
  return opening;
}

/** Give the vector, of length 1, of a prepared photo. */
export async function embed(
  session: InferenceSession,
  pixels: Float32Array,
): Promise<Float32Array> {
  const input = new Tensor('float32', pixels, [1, 3, SIDE, SIDE]);
  const output = await session.run({ pixels: input });
  return output.embedding.data as Float32Array;
}
