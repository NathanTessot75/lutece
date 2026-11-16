import { SymbolView } from 'expo-symbols';
import { useState } from 'react';
import { FlatList, Image, StyleSheet, View, useWindowDimensions } from 'react-native';

import { useTheme } from '@/lib/theme';

// The plate is four units wide for three high, like the drawings.
const HEIGHT_PER_WIDTH = 0.75;
const DOT_SIZE = 7;

type Slide = { kind: 'drawing' } | { kind: 'own'; uri: string };

/**
 * The plate at the top of the page of a monument: its drawing, then the
 * photo the player took when capturing it, with dots telling there are two.
 * Until the drawings are made, a sheet of paper with a faint monument stands
 * for the drawing.
 */
export function Plate({ ownPhoto }: { ownPhoto: string | null }) {
  const theme = useTheme();
  const { width } = useWindowDimensions();
  const height = width * HEIGHT_PER_WIDTH;
  const [shown, setShown] = useState(0);
  const slides: Slide[] = [
    { kind: 'drawing' },
    ...(ownPhoto === null ? [] : [{ kind: 'own' as const, uri: ownPhoto }]),
  ];
  return (
    <View>
      <FlatList
        data={slides}
        keyExtractor={(slide) => slide.kind}
        renderItem={({ item }) =>
          item.kind === 'own' ? (
            <Image
              source={{ uri: item.uri }}
              style={{ width, height, backgroundColor: theme.separator }}
              resizeMode="cover"
              accessibilityLabel="Votre photo"
              accessibilityIgnoresInvertColors
            />
          ) : (
            <View style={[styles.paper, { width, height, backgroundColor: theme.surface }]}>
              <SymbolView
                name="building.columns.fill"
                size={height * 0.42}
                tintColor={theme.separator}
                type="monochrome"
              />
            </View>
          )
        }
        horizontal
        pagingEnabled
        scrollEnabled={slides.length > 1}
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={({ nativeEvent }) =>
          setShown(Math.round(nativeEvent.contentOffset.x / width))
        }
      />
      {slides.length > 1 && (
        <View style={styles.dots} accessible accessibilityLabel={`Image ${shown + 1} sur ${slides.length}`}>
          {slides.map((slide, index) => (
            <View
              key={slide.kind}
              style={[
                styles.dot,
                { backgroundColor: index === shown ? theme.text : theme.muted },
              ]}
            />
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  paper: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  dots: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 7,
    paddingTop: 12,
  },
  dot: {
    width: DOT_SIZE,
    height: DOT_SIZE,
    borderRadius: DOT_SIZE / 2,
  },
});
