# -*- coding: utf-8 -*-
"""
Created on Tue Aug 12 12:48:00 2025

@author: KRHE
"""

import requests
import geopandas as gpd
import pandas as pd

BASE = "https://nve.geodataonline.no/arcgis/rest/services/Nettanlegg4/MapServer"

# Norske navn per lag-ID
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
    # ---- Faste valg ----
    layers = (0, 1, 2, 3, 4, 5)
    where = "1=1"
    page_size = 1000
    # ---------------------

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
                "inSR": 25833,  # bbox er i UTM33N
                "spatialRel": "esriSpatialRelIntersects",
                "returnGeometry": "true",
                "resultOffset": offset,
                "resultRecordCount": page_size,
            }
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            feats = data.get("features", [])
            if not feats:
                break

            # GeoJSON fra ArcGIS er i EPSG:4326 -> projiser til EPSG:25833
            gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326").to_crs("EPSG:25833")
            gdf["nve_lag_id"] = layer
            gdf["nve_lag_navn"] = LAG_NAVN.get(layer, f"Lag {layer}")
            frames.append(gdf)

            if len(feats) < page_size:
                break
            offset += page_size

    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:25833")

    out = pd.concat(frames, ignore_index=True)
    return out  # EPSG:25833
        