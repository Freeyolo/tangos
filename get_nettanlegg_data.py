# -*- coding: utf-8 -*-
"""
Created on Tue Aug 12 12:48:00 2025

@author: KRHE
"""

import requests
import geopandas as gpd
import pandas as pd

BASE = "https://nve.geodataonline.no/arcgis/rest/services/Nettanlegg4/MapServer"

LAG_NAVN = {
    0: "Transmisjonsnett (luftledning)",
    1: "Regionalnett (luftledning)",
    2: "Distribusjonsnett",
    3: "Sjøkabel",
    4: "Mast/linjepunkt",
    5: "Stasjon/transformatorstasjon",
}

def get_nettanlegg_data(row):
    """
    Henter objekter fra NVE Nettanlegg (lag 0–5) som krysser en bbox i EPSG:25833
    og returnerer en GeoDataFrame i EPSG:25833 (UTM33N).
    """
    layers = (0, 1, 2, 3, 4, 5)
    where = "1=1"
    page_size = 1000

    minx, miny, maxx, maxy = row["minx"], row["miny"], row["maxx"], row["maxy"]
    envelope = f"{minx},{miny},{maxx},{maxy}"  # EPSG:25833

    frames = []
    for layer in layers:
        url = f"{BASE}/{layer}/query"
        offset = 0
        while True:
            params = {
                "f": "geojson",
                "where": where,
                "outFields": "*",
                "geometry": envelope,
                "geometryType": "esriGeometryEnvelope",
                "inSR": 25833,
                "outSR": 4326,                       # be explicit: GeoJSON in WGS84
                "orderByFields": "OBJECTID",         # stable paging
                "spatialRel": "esriSpatialRelIntersects",
                "returnGeometry": "true",
                "returnM": False,
                "returnZ": False,
                "resultType": "standard",
                "maxAllowableOffset": 0.0001,        # ~11 m in degrees; keeps HTML small
                "resultOffset": offset,
                "resultRecordCount": page_size,
            }
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            feats = data.get("features", [])
            if not feats:
                break

            # Read in WGS84 and convert to UTM33N for internal consistency
            gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326").to_crs("EPSG:25833")
            gdf["nve_lag_id"] = layer
            gdf["nve_lag_navn"] = LAG_NAVN.get(layer, f"Lag {layer}")
            frames.append(gdf)

            # robust break condition
            exceeded = data.get("exceededTransferLimit")
            if len(feats) < page_size or (exceeded is False):
                break
            offset += page_size

    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:25833")

    return pd.concat(frames, ignore_index=True)
        