"""Decode a byte-ranged GFS GRIB message at the nearest Melbourne grid point."""

from __future__ import annotations

from typing import Any

from eccodes import (
    codes_get,
    codes_grib_find_nearest,
    codes_new_from_message,
    codes_release,
)


def decode_nearest(
    message: bytes, station_latitude: float, station_longitude: float
) -> dict[str, Any]:
    """Decode one complete GRIB2 message and nearest value in native units."""
    handle = codes_new_from_message(message)
    if handle is None:
        raise RuntimeError("FAIL_GFS_DECODER: eccodes returned no message handle")
    try:
        nearest = codes_grib_find_nearest(
            handle, station_latitude, station_longitude
        )[0]
        return {
            "short_name": str(codes_get(handle, "shortName")),
            "name": str(codes_get(handle, "name")),
            "units": str(codes_get(handle, "units")),
            "type_of_level": str(codes_get(handle, "typeOfLevel")),
            "level": float(codes_get(handle, "level")),
            "value": float(nearest["value"]),
            "grid_latitude": float(nearest["lat"]),
            "grid_longitude": float(nearest["lon"]),
            "distance_km": float(nearest["distance"]),
        }
    except Exception as error:
        raise RuntimeError(f"FAIL_GFS_DECODER: {error}") from error
    finally:
        codes_release(handle)
