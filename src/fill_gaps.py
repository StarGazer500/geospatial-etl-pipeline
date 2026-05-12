# -*- coding: utf-8 -*-
"""
fill_gaps_geopandas.py
======================
Standalone GeoPandas rewrite of the QGIS "Fill Gaps" plugin
(original by Antonio Sobral Almeida, GPL-2).

Usage as a function
-------------------
    from fill_gaps_geopandas import fill_gaps
    import geopandas as gpd

    gdf    = gpd.read_file("parcels.gpkg")       # any CRS, including EPSG:4326
    result = fill_gaps(gdf, max_gap_area=500)    # max_gap_area always in m²
    result.to_file("parcels_filled.gpkg")        # returned in original CRS

Dependencies
------------
    pip install geopandas shapely pyproj
"""

import geopandas as gpd
import pandas as pd
from pyproj import CRS
from shapely import set_precision
from shapely.validation import make_valid
from shapely.geometry import MultiPolygon, Polygon


# ---------------------------------------------------------------------------
# UTM estimator
# ---------------------------------------------------------------------------

def estimate_utm_crs(gdf: gpd.GeoDataFrame) -> CRS:
    """Return the UTM CRS that best covers the layer centroid."""
    centroid = gdf.geometry.union_all().centroid
    if not gdf.crs.is_geographic:
        centroid = (
            gpd.GeoSeries([centroid], crs=gdf.crs)
            .to_crs("EPSG:4326")
            .iloc[0]
        )
    lon, lat = centroid.x, centroid.y
    zone = int((lon + 180) / 6) + 1
    base = 32600 if lat >= 0 else 32700
    epsg = base + zone
    print(f"  Estimated UTM CRS: EPSG:{epsg}  (zone {zone}{'N' if lat >= 0 else 'S'})")
    return CRS.from_epsg(epsg)


# ---------------------------------------------------------------------------
# Overlap resolver
# ---------------------------------------------------------------------------

def resolve_overlaps(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Remove overlaps between polygons while preserving all features.

    For each overlapping pair, the overlap area is subtracted from the
    smaller polygon (smaller yields to larger). Uses a spatial index so
    only true candidate pairs are checked — O(n log n) not O(n²).

    Returns the same GeoDataFrame with non-overlapping geometries.
    Rows that become empty after clipping are dropped.
    """
    geom_col = gdf.geometry.name
    geoms = [
        make_valid(set_precision(g, 0.001)) if g is not None else None
        for g in gdf.geometry
    ]
    sindex = gdf.sindex

    for i, geom_i in enumerate(geoms):
        if geom_i is None or geom_i.is_empty:
            continue

        candidates = [
            j for j in sindex.intersection(geom_i.bounds)
            if j != i and geoms[j] is not None and not geoms[j].is_empty
        ]

        for j in candidates:
            geom_j = geoms[j]
            if not geom_i.intersects(geom_j):
                continue

            overlap = geom_i.intersection(geom_j)
            if overlap.is_empty or overlap.area < 1e-8:
                continue

            if geom_i.area <= geom_j.area:
                geoms[i] = make_valid(geom_i.difference(geom_j))
                geom_i   = geoms[i]
                if geom_i.is_empty:
                    break
            else:
                geoms[j] = make_valid(geom_j.difference(geom_i))

    result = gdf.copy()
    result[geom_col] = geoms
    result = result[result.geometry.notna() & ~result.geometry.is_empty]
    result = result[result.geometry.area > 0]
    return result.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Core algorithm
# ---------------------------------------------------------------------------

def fill_gaps(
    gdf: gpd.GeoDataFrame,
    outer_buffer: float = 10.0,
    max_gap_area: float | None = None,
    fix_overlaps: bool = True,
) -> gpd.GeoDataFrame:
    """
    Fill interior gaps in a polygon GeoDataFrame.

    Parameters
    ----------
    gdf          : Input polygon GeoDataFrame. Any CRS accepted.
                   Geographic CRS (e.g. EPSG:4326) is auto-reprojected to the
                   estimated UTM zone and back.
    outer_buffer : Buffer distance in metres for the outer envelope
                   (mirrors 10 / 7 / 5 m triple-buffer in the original plugin).
                   Must be > 5.  Default: 10.
    max_gap_area : Maximum gap area in m² to fill. Gaps larger than this are
                   left untouched.  None → fill all interior gaps.
    fix_overlaps : If True (default), overlapping polygons are resolved before
                   gap detection so overlaps don't hide gaps. Smaller polygon
                   yields to the larger one in each overlapping pair.
                   Set to False only if you are certain the data is clean.

    Returns
    -------
    GeoDataFrame in the same CRS as the input, with interior gaps appended.
    """

    if outer_buffer <= 5:
        raise ValueError("outer_buffer must be > 5.")

    original_crs = gdf.crs

    # ------------------------------------------------------------------
    # Step 1 – Fix invalid geometries
    # ------------------------------------------------------------------
    print("  Fixing geometries …")
    working = gdf.copy()
    geom_col = working.geometry.name
    working[geom_col] = working.geometry.apply(
        lambda g: make_valid(g) if g is not None and not g.is_valid else g
    )
    working = working[~working.geometry.is_empty & working.geometry.notna()].reset_index(drop=True)

    # ------------------------------------------------------------------
    # Step 2 – Reproject to metric CRS if input is geographic
    # ------------------------------------------------------------------
    utm_crs = None
    if working.crs is None or working.crs.is_geographic:
        utm_crs = estimate_utm_crs(working)
        print("  Reprojecting to UTM …")
        working = working.to_crs(utm_crs)

    # ------------------------------------------------------------------
    # Step 3 – Resolve overlaps so they don't hide gaps during union
    # ------------------------------------------------------------------
    if fix_overlaps:
        union_area  = working.geometry.union_all().area
        total_area  = working.geometry.area.sum()
        overlap_m2  = total_area - union_area

        if overlap_m2 > 1.0:
            print(f"  Overlap detected: {overlap_m2:,.1f} m² across layer — resolving …")
            working = resolve_overlaps(working)
            print(f"  Overlaps resolved. Features remaining: {len(working)}")
        else:
            print("  No significant overlaps detected.")

    # ------------------------------------------------------------------
    # Step 4 – Union all polygons into one geometry (fast single diff)
    # ------------------------------------------------------------------
    print("  Unioning polygons …")
    layer_union = working.geometry.union_all()

    # ------------------------------------------------------------------
    # Step 5 – Bounding box + three square-capped buffers
    # ------------------------------------------------------------------
    bbox         = layer_union.envelope
    big_box_geom = bbox.buffer(outer_buffer,       cap_style=3)   # 10 m
    mid_box_geom = bbox.buffer(outer_buffer - 3.0, cap_style=3)   #  7 m
    sml_box_geom = bbox.buffer(outer_buffer - 5.0, cap_style=3)   #  5 m

    # ------------------------------------------------------------------
    # Step 6 – All voids = big_box MINUS union (single fast shapely op)
    # ------------------------------------------------------------------
    print("  Computing voids …")
    layer_union = make_valid(layer_union)
    all_voids_geom = big_box_geom.difference(layer_union)

    # ------------------------------------------------------------------
    # Step 7 – Outer ring = mid_box MINUS sml_box (2 m-wide frame)
    # ------------------------------------------------------------------
    outer_ring_geom = mid_box_geom.difference(sml_box_geom)

    # ------------------------------------------------------------------
    # Step 8 – Explode multipart voids to individual polygons
    # ------------------------------------------------------------------
    if isinstance(all_voids_geom, Polygon):
        void_list = [all_voids_geom]
    elif isinstance(all_voids_geom, MultiPolygon):
        void_list = list(all_voids_geom.geoms)
    else:
        void_list = [g for g in all_voids_geom.geoms
                     if isinstance(g, (Polygon, MultiPolygon))]

    void_list = [g for g in void_list if not g.is_empty and g.area > 0]

    # ------------------------------------------------------------------
    # Step 9 – Keep only voids DISJOINT from the outer ring (true interior gaps)
    # ------------------------------------------------------------------
    interior_gaps = [g for g in void_list if g.disjoint(outer_ring_geom)]
    print(f"  Interior gaps detected: {len(interior_gaps)}")

    # ------------------------------------------------------------------
    # Step 10 – Area filter (UTM → area is always in m²)
    # ------------------------------------------------------------------
    if max_gap_area is not None and interior_gaps:
        before = len(interior_gaps)
        interior_gaps = [g for g in interior_gaps if g.area <= max_gap_area]
        print(f"  Skipped (area > {max_gap_area} m²): {before - len(interior_gaps)}")
        print(f"  Will fill: {len(interior_gaps)}")

    if not interior_gaps:
        print("  No interior gaps to fill – returning layer.")
        result = working
    else:
        # ------------------------------------------------------------------
        # Step 11 – Append gap polygons to the layer
        # ------------------------------------------------------------------
        geom_col = working.geometry.name
        gaps_gdf = gpd.GeoDataFrame(
            [{col: None for col in working.columns if col != geom_col}
             | {geom_col: g}
             for g in interior_gaps],
            geometry=geom_col,
            crs=working.crs,
        )

        result = gpd.GeoDataFrame(
            pd.concat([working, gaps_gdf], ignore_index=True),
            crs=working.crs,
            geometry=geom_col,
        )

        drop_cols = {"width", "height", "perimeter", "path"}
        result = result.drop(columns=[c for c in drop_cols if c in result.columns])

    # ------------------------------------------------------------------
    # Step 12 – Reproject back to original CRS
    # ------------------------------------------------------------------
    if utm_crs is not None:
        print("  Reprojecting back to original CRS …")
        result = result.to_crs(original_crs)

    return result
