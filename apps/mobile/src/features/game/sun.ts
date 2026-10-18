import type { Coordinates } from '@/features/capture/geometry';

// The sun is up when its top edge crosses the horizon, light bent by the air.
const HORIZON_ZENITH_DEG = 90.833;
const MINUTE_MS = 60_000;

const toRadians = (degrees: number) => (degrees * Math.PI) / 180;
const toDegrees = (radians: number) => (radians * 180) / Math.PI;

export type SunTimes = { sunrise: Date; sunset: Date };

/**
 * When the sun rises and sets on the day, in UTC, of a moment, at a place:
 * the general formulas of the NOAA, right within a minute or two. None where
 * the sun does not rise or does not set.
 */
export function sunTimes(at: Date, place: Coordinates): SunTimes | null {
  const year = at.getUTCFullYear();
  const midnight = Date.UTC(year, at.getUTCMonth(), at.getUTCDate());
  const dayOfYear = Math.round((midnight - Date.UTC(year, 0, 1)) / (1440 * MINUTE_MS)) + 1;
  const daysInYear = Date.UTC(year + 1, 0, 1) - Date.UTC(year, 0, 1) === 366 * 1440 * MINUTE_MS ? 366 : 365;
  const angle = ((2 * Math.PI) / daysInYear) * (dayOfYear - 1);
  const equationOfTime =
    229.18 *
    (0.000075 +
      0.001868 * Math.cos(angle) -
      0.032077 * Math.sin(angle) -
      0.014615 * Math.cos(2 * angle) -
      0.040849 * Math.sin(2 * angle));
  const declination =
    0.006918 -
    0.399912 * Math.cos(angle) +
    0.070257 * Math.sin(angle) -
    0.006758 * Math.cos(2 * angle) +
    0.000907 * Math.sin(2 * angle) -
    0.002697 * Math.cos(3 * angle) +
    0.00148 * Math.sin(3 * angle);
  const latitude = toRadians(place.latitude);
  const cosHourAngle =
    Math.cos(toRadians(HORIZON_ZENITH_DEG)) / (Math.cos(latitude) * Math.cos(declination)) -
    Math.tan(latitude) * Math.tan(declination);
  if (cosHourAngle < -1 || cosHourAngle > 1) {
    return null;
  }
  const hourAngle = toDegrees(Math.acos(cosHourAngle));
  const minutes = (sign: number) =>
    720 - 4 * (place.longitude + sign * hourAngle) - equationOfTime;
  return {
    sunrise: new Date(midnight + minutes(1) * MINUTE_MS),
    sunset: new Date(midnight + minutes(-1) * MINUTE_MS),
  };
}
