"""Geographic helpers shared by the pipeline steps."""

from collections.abc import Mapping, Sequence
from typing import Any

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

WGS84 = "EPSG:4326"
LAMBERT_93 = "EPSG:2154"  # the metric projection used in France

# Generous bounding box around Paris, both woods included, used to reject bogus points.
PARIS_LAT_RANGE = (48.80, 48.91)
PARIS_LON_RANGE = (2.22, 2.48)


def is_in_paris(lat: float, lon: float) -> bool:
    """Tell whether a WGS84 point falls inside the Paris bounding box."""
    return (
        PARIS_LAT_RANGE[0] <= lat <= PARIS_LAT_RANGE[1]
        and PARIS_LON_RANGE[0] <= lon <= PARIS_LON_RANGE[1]
    )


def project_points(
    records: Sequence[Mapping[str, Any]], key: str
) -> dict[str, BaseGeometry]:
    """Project the records that have coordinates to Lambert-93, by identifier."""
    located = [record for record in records if record["lat"] is not None]
    points = gpd.GeoSeries(
        gpd.points_from_xy(
            [record["lon"] for record in located], [record["lat"] for record in located]
        ),
        crs=WGS84,
    ).to_crs(LAMBERT_93)
    return {record[key]: point for record, point in zip(located, points, strict=True)}
