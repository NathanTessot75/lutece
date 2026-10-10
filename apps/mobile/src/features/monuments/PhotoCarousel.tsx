import { useState } from 'react';
import {
  FlatList,
  Image,
  Linking,
  Pressable,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';

import type { MonumentPhoto } from '@/db/monuments';
import { type Theme, useTheme } from '@/lib/theme';

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

/** The photos of a monument, side by side, each with its author and licence. */
export function PhotoCarousel({ photos }: { photos: MonumentPhoto[] }) {
  const theme = useTheme();
  const { width } = useWindowDimensions();
  const [shown, setShown] = useState(0);

  if (photos.length === 0) {
    return <Placeholder text="Pas encore de photo" width={width} theme={theme} />;
  }
  return (
    <View>
      <FlatList
        data={photos}
        keyExtractor={(photo) => String(photo.rank)}
        renderItem={({ item }) => <Photo photo={item} width={width} theme={theme} />}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={({ nativeEvent }) =>
          setShown(Math.round(nativeEvent.contentOffset.x / width))
        }
      />
      {photos.length > 1 && (
        <View style={styles.counter}>
          <Text style={styles.counterText}>
            {shown + 1} / {photos.length}
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
