"""Geographic helpers shared by the pipeline steps."""

# Generous bounding box around Paris, both woods included, used to reject bogus points.
PARIS_LAT_RANGE = (48.80, 48.91)
PARIS_LON_RANGE = (2.22, 2.48)


def is_in_paris(lat: float, lon: float) -> bool:
    """Tell whether a WGS84 point falls inside the Paris bounding box."""
    return (
        PARIS_LAT_RANGE[0] <= lat <= PARIS_LAT_RANGE[1]
        and PARIS_LON_RANGE[0] <= lon <= PARIS_LON_RANGE[1]
    )
