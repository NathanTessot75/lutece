import { useState } from 'react';
import { FlatList, Image, Linking, Pressable, StyleSheet, View, useWindowDimensions } from 'react-native';

import type { MonumentPhoto } from '@/db/monuments';
import { type Theme, useTheme } from '@/lib/theme';
import { Text } from '@/lib/typography';

// Photos are shown four units wide for three high, whatever their own shape.
const HEIGHT_PER_WIDTH = 0.75;

function credit(photo: MonumentPhoto): string {
  return [photo.author ?? 'Auteur inconnu', photo.licence, 'Wikimedia Commons']
    .filter(Boolean)
    .join(' · ');
}

function Placeholder({ text, width, theme }: { text: string; width: number; theme: Theme }) {
  return (
    <View
      style={[
        styles.placeholder,
        { width, height: width * HEIGHT_PER_WIDTH, backgroundColor: theme.separator },
      ]}
    >
      <Text style={[styles.placeholderText, { color: theme.secondaryText }]}>{text}</Text>
    </View>
  );
}

function Photo({ photo, width, theme }: { photo: MonumentPhoto; width: number; theme: Theme }) {
  // The photos are fetched from Wikimedia: without a connection they are missing.
  const [failed, setFailed] = useState(false);
  return (
    <View style={{ width }}>
      {failed ? (
        <Placeholder text="Photo indisponible hors connexion" width={width} theme={theme} />
      ) : (
        <Image
          source={{ uri: photo.thumbUrl }}
          style={{ width, height: width * HEIGHT_PER_WIDTH, backgroundColor: theme.separator }}
          resizeMode="cover"
          onError={() => setFailed(true)}
          accessibilityIgnoresInvertColors
        />
      )}
      <Pressable onPress={() => void Linking.openURL(photo.pageUrl)} accessibilityRole="link">
        <Text style={[styles.credit, { color: theme.secondaryText }]} numberOfLines={1}>
          {credit(photo)}
        </Text>
      </Pressable>
    </View>
  );
}

/** The picture that the player took when capturing the monument. */
export type OwnPhoto = {
  uri: string;
  caption: string;
};

function Own({ photo, width, theme }: { photo: OwnPhoto; width: number; theme: Theme }) {
  return (
    <View style={{ width }}>
      <Image
        source={{ uri: photo.uri }}
        style={{ width, height: width * HEIGHT_PER_WIDTH, backgroundColor: theme.separator }}
        resizeMode="cover"
        accessibilityIgnoresInvertColors
      />
      <Text style={[styles.credit, { color: theme.secondaryText }]} numberOfLines={1}>
        {photo.caption}
      </Text>
    </View>
  );
}

type Props = {
  photos: MonumentPhoto[];
  own?: OwnPhoto | null;
};

/**
 * The photos of a monument, side by side: the one of the player first, then
 * the reference ones, each with its author and licence.
 */
export function PhotoCarousel({ photos, own = null }: Props) {
  const theme = useTheme();
  const { width } = useWindowDimensions();
  const [shown, setShown] = useState(0);
  const slides = [...(own ? [own] : []), ...photos];

  if (slides.length === 0) {
    return <Placeholder text="Pas encore de photo" width={width} theme={theme} />;
  }
  return (
    <View>
      <FlatList
        data={slides}
        keyExtractor={(slide) => ('uri' in slide ? 'own' : String(slide.rank))}
        renderItem={({ item }) =>
          'uri' in item ? (
            <Own photo={item} width={width} theme={theme} />
          ) : (
            <Photo photo={item} width={width} theme={theme} />
          )
        }
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={({ nativeEvent }) =>
          setShown(Math.round(nativeEvent.contentOffset.x / width))
        }
      />
      {slides.length > 1 && (
        <View style={styles.counter}>
          <Text style={styles.counterText}>
            {shown + 1} / {slides.length}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  placeholder: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  placeholderText: {
    fontSize: 15,
  },
  credit: {
    fontSize: 12,
    paddingHorizontal: 16,
    paddingTop: 6,
  },
  counter: {
    position: 'absolute',
    top: 12,
    right: 12,
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
    backgroundColor: 'rgba(0, 0, 0, 0.55)',
  },
  counterText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '600',
  },
});
