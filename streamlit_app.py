# -*- coding: utf-8 -*-
"""
Created on Mon Dec 18 14:32:06 2023
Program som tar et koordinat (EPSG:32633 – WGS 84 / UTM zone 33N) og en eksplosivmengde og finner alle bygninger innenfor hensynssonen.
@author: KRHE
"""

import pandas as pd
import geopandas as gpd
import folium
import os
import requests
import streamlit as st
from streamlit_folium import st_folium
from io import BytesIO

cwd = os.getcwd()
# nording = input("UTM33N NORD  koordinat:")
# oesting = input("UTM33 ØST koordinat:")
# NEI = float(input("Netto eksplosivinnhold:"))

nording = 6627962
oesting = 204012
NEI = 12920


d = {'nording':[nording],'oesting':[oesting],'NEI':[NEI]}
df = pd.DataFrame(data=d)
gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.oesting,df.nording),crs='EPSG:32633')

# =============================================================================
# denne funksjonen tar netto eksplosivinnhold (NEI) som argument og returnerer sikkerhetsavstanden 
# (QD, Quantity Distance) for hhv. sykehus, bolig og vei. QD er definert i eksplosivforskriften § 37 
# =============================================================================
def QD_func(NEI):
    QD_syk = round(44.4*NEI**(1/3))
    QD_bolig = round(22.2*NEI**(1/3))
    QD_vei = round(14.8*NEI**(1/3))
    return QD_syk, QD_bolig, QD_vei

QD_syk, QD_bolig, QD_vei = QD_func(NEI)

gdf_syk = gdf.copy()
gdf_syk['QD_syk'] = QD_syk
gdf_syk['geometry'] = gdf_syk['geometry'].buffer(gdf_syk['QD_syk'])
gdf_bolig = gdf.copy()
gdf_bolig['QD_bolig'] = QD_bolig
gdf_bolig['geometry'] = gdf_bolig['geometry'].buffer(gdf_bolig['QD_bolig'])
gdf_vei = gdf.copy()
gdf_vei['QD_vei'] = QD_vei
gdf_vei['geometry'] = gdf_vei['geometry'].buffer(gdf_vei['QD_vei'])

# =============================================================================
# Lage en firkantet bounding boks for QD_syk, denne vil også inneholde QD_bolig og QD_vei
# =============================================================================
gdf_syk_bbox = pd.concat([gdf_syk, gdf_syk['geometry'].bounds], axis=1) #lager en firkantet bounding box for de sirkulære sikkerhetsavstandene


# =============================================================================
# Denne funksjonen bruker kartverkets API til å finne alle bygninger innenfor en bounding box
# =============================================================================

def get_geo_data(row):
    wfs_url = "https://wfs.geonorge.no/skwms1/wfs.matrikkelen-bygningspunkt?"
    
    minx = row['minx']
    miny = row['miny']
    maxx = row['maxx']
    maxy = row['maxy']
    
    bbox_str = f'{minx},{miny},{maxx},{maxy},EPSG:32633'

    params = {
        'service': 'WFS',
        'version': '2.0.0',
        'request': 'GetFeature',
        'typename': 'app:Bygning',
        'srsname': 'EPSG:32633',
        'outputformat': 'application/gml+xml; version=3.2',
        'bbox': bbox_str,
        #'count': '100', reduce output count
    }


    try:
        response = requests.get(wfs_url, params=params)
        response.raise_for_status()  # Raises HTTPError for bad responses
    except requests.exceptions.HTTPError as errh:
        print ("HTTP Error:",errh)
    except requests.exceptions.ConnectionError as errc:
        print ("Error Connecting:",errc)
    except requests.exceptions.Timeout as errt:
        print ("Timeout Error:",errt)
    except requests.exceptions.RequestException as err:
        print ("Error:",err)
        
    try:
        # Load the GML response into a GeoDataFrame
        geo_data = gpd.read_file(BytesIO(response.content))
        return geo_data
    except ValueError as ve:
        # Handle ValueError, print the error message, and return an empty GeoDataFrame
        print(f"ValueError: {ve}")
        return gpd.GeoDataFrame()
    except Exception as e:
        # Handle other exceptions, print the error message, and return an empty GeoDataFrame
        print(f"An unexpected error occurred: {e}")
        return gpd.GeoDataFrame()
    
result_geodataframe = pd.concat([get_geo_data(row) for index, row in gdf_syk_bbox.iterrows()], ignore_index=True)
eksponerte_bygg_syk = gpd.sjoin(result_geodataframe,gdf_syk,predicate='within') # finner bygninger fra matrikkelen innenfor sikkerhetsavstanden

# =============================================================================
# Plotting av data i kart og lagring av kartet
# =============================================================================
kartpunkt = gdf.explore(marker_type='marker',style_kwds=dict(color="black"))
kartQDsyk = gdf_syk.explore(m=kartpunkt,style_kwds=dict(fill=False,color='red'))
kartQDbol = gdf_bolig.explore(m=kartpunkt,style_kwds=dict(fill=False,color='orange'))
kartQDvei = gdf_vei.explore(m=kartpunkt,style_kwds=dict(fill=False,color='yellow'))
kart2 = eksponerte_bygg_syk.explore(m=kartpunkt,style_kwds=dict(color="red"))
ut = os.path.join(cwd, r'kart2.html')
kart2.save(ut)
# Vise kart i streamlit med folium
st_data = st_folium(kart2, width=725)
# =============================================================================
# Eksportering av data i CSV format
# =============================================================================
utbane = os.path.join(cwd, r'eksponerte_bygg_qd_syk.csv')
eksponerte_bygg_syk.to_csv(utbane)
