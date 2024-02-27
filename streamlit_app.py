# -*- coding: utf-8 -*-
"""
Created on Mon Dec 18 14:32:06 2023
Program som tar et koordinat (EPSG:32633 – WGS 84 / UTM zone 33N) og en eksplosivmengde og finner alle bygninger innenfor hensynssonen.
@author: KRHE
"""

import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
import os
import requests
from shapely import wkt
import streamlit as st
from io import BytesIO

# st.set_page_config(layout="wide") #wide mode

from streamlit_folium import st_folium

output = pd.DataFrame()
output_csv = pd.DataFrame()
bygningstype_url = 'https://raw.githubusercontent.com/Freeyolo/tangos/main/bygningstype.csv'
   
# =============================================================================
# denne funksjonen tar netto eksplosivinnhold (NEI) som argument og returnerer sikkerhetsavstanden 
# (QD, Quantity Distance) for hhv. sykehus, bolig og vei. QD er definert i eksplosivforskriften § 37 
# =============================================================================
def QD_func(NEI):
    QD_syk = max(round(44.4 * NEI ** (1/3)), 800)
    QD_bolig = max(round(22.2 * NEI ** (1/3)), 400)
    QD_vei = max(round(14.8 * NEI ** (1/3)), 180)
    return QD_syk, QD_bolig, QD_vei

# Define colors for each building group to be used later one color for each group in 
# https://www.ssb.no/klass/klassifikasjoner/31

with st.form("my_form"):
   st.write("Input data")
   nording = st.text_input('Nording',value=None,placeholder='EPSG:32633 - WGS 84 / UTM zone 33N')
   oesting = st.text_input('Østing',value=None,placeholder='EPSG:32633 - WGS 84 / UTM zone 33N')
   NEI = st.number_input('Totalvekt', value=None,step=500, max_value=100000, placeholder='Netto eksplosivinnhold i kg')

   # Every form must have a submit button.
   submitted = st.form_submit_button("Submit")
   if submitted:
    d = {'nording':[nording],'oesting':[oesting],'NEI':[NEI]}
    df = pd.DataFrame(data=d)
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.oesting,df.nording),crs='EPSG:32633')
       
    QD_syk, QD_bolig, QD_vei = QD_func(NEI)

    #en geopandas geodataframe kan kun ha en "geometry" kolonne, derfor er det nødvendig å kopiere gdf tre ganger

    gdf_syk = gdf.copy().drop(columns=['nording','oesting'])
    gdf_bolig = gdf.copy().drop(columns=['nording','oesting'])
    gdf_vei = gdf.copy().drop(columns=['nording','oesting'])

    gdf_syk['QD_syk'] = QD_syk
    gdf_bolig['QD_bolig'] = QD_bolig
    gdf_vei['QD_vei'] = QD_vei
    
    gdf_syk['geometry'] = gdf_syk['geometry'].buffer(gdf_syk['QD_syk'])  
    gdf_bolig['geometry'] = gdf_bolig['geometry'].buffer(gdf_bolig['QD_bolig'])
    gdf_vei['geometry'] = gdf_vei['geometry'].buffer(gdf_vei['QD_vei'])
    
    #dette er kartpunktet for lageret
    kartpunkt = gdf.explore(marker_type='marker',name='anlegg',control=False)

    # =============================================================================
    # Lage en firkantet bounding boks for QD_syk, denne vil også inneholde QD_bolig og QD_vei
    # =============================================================================
    gdf_syk_bbox = pd.concat([gdf_syk, gdf_syk['geometry'].bounds], axis=1) #lager en firkantet bounding box for de sirkulære sikkerhetsavstandene
    gdf_vei_bbox = pd.concat([gdf_vei, gdf_vei['geometry'].bounds], axis=1) #lager en firkantet bounding box for de sirkulære sikkerhetsavstandene  
    
    def get_matrikkel_data(row):
        # =============================================================================
        # Denne funksjonen bruker kartverkets API til å finne alle bygninger innenfor en bounding box
        # =============================================================================
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
            matrikkel_data = gpd.read_file(BytesIO(response.content))
            return matrikkel_data
        except ValueError as ve:
            # Handle ValueError, print the error message, and return an empty GeoDataFrame
            print(f"ValueError: {ve}")
            return gpd.GeoDataFrame()
        except Exception as e:
            # Handle other exceptions, print the error message, and return an empty GeoDataFrame
            print(f"An unexpected error occurred: {e}")
            return gpd.GeoDataFrame()

    result_geodataframe = get_matrikkel_data(gdf_syk_bbox.iloc[0])
    
    def get_veg_data(row):
        # =============================================================================
        # Denne funksjonen bruker SVV NVDB API til å finne alle veier og ÅDT innenfor en bounding box
        # https://nvdbapiles-v3.atlas.vegvesen.no/dokumentasjon/
        # =============================================================================
        nvdburl = 'https://nvdbapiles-v3.atlas.vegvesen.no/vegobjekter/540' #540 er ÅDT
        minx = row['minx']
        miny = row['miny']
        maxx = row['maxx']
        maxy = row['maxy']

        headers = {
        'accept': 'application/vnd.vegvesen.nvdb-v3-rev1+json',
        'X-Client': 'Utdrag ÅDT',
        'X-Client-Session': '402b9aee-16f9-e38d-2ce7-cd6bc20eb3e3'
        }
        params = {
            'srid': '5973',
            'inkluder': 'alle',
            'segmentering': 'true',
            'kartutsnitt': f'{minx},{miny},{maxx},{maxy}',
            #'polygon': '20000.0 6520000.0,20500.0 6520000.0,21000.0 6500000.0,20000.0 6520000.0',
        }
        try:
            response = requests.get(nvdburl, params=params, headers=headers)
            response.raise_for_status()  # Raises HTTPError for bad responses
            jsonResponse = response.json()
            
            # Check if the response contains objects
            if 'objekter' not in jsonResponse:
                return gpd.GeoDataFrame()  # Return empty GeoDataFrame if no objects
            
        except requests.exceptions.RequestException as err:
            print ("Error:", err)
            return gpd.GeoDataFrame()  # Return empty GeoDataFrame on error
        except ValueError as v_err:
            print ("Error decoding JSON:", v_err)
            return gpd.GeoDataFrame()  # Return empty GeoDataFrame if JSON decoding fails
            
        # Initialize an empty list to store dictionaries
        vegdata_list = []
        # Iterate through jsonResponse['objekter']
        for vegobjekt in jsonResponse['objekter']:
            vegdata_dict = {'Vegobj_id': vegobjekt['id']}
            
            # Check if the 'geometry' key exists in vegobjekt
            if 'geometri' in vegobjekt and 'wkt' in vegobjekt['geometri']:
                vegdata_dict['geometry'] = vegobjekt['geometri']['wkt']
            
            # Append the dictionary to the list
            vegdata_list.append(vegdata_dict)

            for egenskap in vegobjekt['egenskaper']:
                if egenskap['id'] == 4621:
                    vegdata_dict['ÅDT_år'] = egenskap['verdi']
                if egenskap['id'] == 4623:
                    vegdata_dict['ÅDT_total'] = egenskap['verdi']
                if egenskap['id'] == 4625:
                    vegdata_dict['ÅDT_grunnlag'] = egenskap['verdi']

        # Create a DataFrame from the list of dictionaries
        vegdata = pd.DataFrame(vegdata_list)
        
        # If the DataFrame is empty, return an empty GeoDataFrame
        if vegdata.empty:
            return gpd.GeoDataFrame()
        
        # If 'geometry' column exists, convert the 'wkt' strings to Shapely geometries
        if 'geometry' in vegdata:
            vegdata['geometry'] = vegdata['geometry'].apply(wkt.loads)
        
        # Create a GeoDataFrame from the DataFrame
        geo_veg_data = gpd.GeoDataFrame(vegdata, geometry='geometry')
        
        return geo_veg_data
            
    result_veg_geodataframe = get_veg_data(gdf_vei_bbox.iloc[0])

    if not result_veg_geodataframe.empty:
        vegsegmenter = result_veg_geodataframe.explode(ignore_index=True)
        vegsegmenter.crs = 'EPSG:32633'
        veg_i_QD = gpd.sjoin(vegsegmenter, gdf_vei, predicate='intersects')
        kart_veg = vegsegmenter.explore(m=kartpunkt,style_kwds=dict(color='black'), name="Vei")

    if not result_geodataframe.empty:
        eksponerte_bygg_syk = gpd.sjoin(result_geodataframe, gdf_syk, predicate='within')
        output = eksponerte_bygg_syk[['bygningstype', 'geometry']]
        bygningstype = pd.read_csv(bygningstype_url, index_col=False, sep=';', usecols=['Navn', 'Kodeverdi'], encoding='utf8')
        output = output.merge(bygningstype, how='left', left_on='bygningstype', right_on='Kodeverdi')
        output.drop(columns=['Kodeverdi'], inplace=True)
        output['bygningstype'] = output['bygningstype'].astype(str) # Convert 'bygningstype' column to string type
        boliger = output[output['bygningstype'].str.startswith('1')]
        industri = output[output['bygningstype'].str.startswith('2')]
        kontor = output[output['bygningstype'].str.startswith('3')]
        samferdsel = output[output['bygningstype'].str.startswith('4')]
        hotell = output[output['bygningstype'].str.startswith('5')]
        kultur = output[output['bygningstype'].str.startswith('6')]
        helse = output[output['bygningstype'].str.startswith('7')]
        brann = output[output['bygningstype'].str.startswith('8')]
        output_csv = pd.DataFrame(output)  # convert back to pandas dataframe

        # =============================================================================
        # Plotting av matrikkeldata i kart og lagring av kartet
        # =============================================================================
        kartQDsyk = gdf_syk.explore(m=kartpunkt,style_kwds=dict(fill=False,color='red'),name ='QDsyk',control=False)
        kartQDbol = gdf_bolig.explore(m=kartpunkt,style_kwds=dict(fill=False,color='orange'),name ='QDbolig',control=False)
        kartQDvei = gdf_vei.explore(m=kartpunkt,style_kwds=dict(fill=False,color='yellow'),name ='QDvei',control=False)
        if not industri.empty:
            kartindustri = industri.explore(m=kartpunkt, style_kwds=dict(color='grey'), name="Industri/lager")
        if not kontor.empty:
            kartkontor = kontor.explore(m=kartpunkt, style_kwds=dict(color='grey'), name="Kontor/forretning")
        if not samferdsel.empty:
            kartsamferdsel = samferdsel.explore(m=kartpunkt, style_kwds=dict(color='grey'), name="Samferdsel")
        if not hotell.empty:
            karthotell = hotell.explore(m=kartpunkt, style_kwds=dict(color='red'), name="Hotell/restaurant")
        if not kultur.empty:
            kartkultur = kultur.explore(m=kartpunkt, style_kwds=dict(color='red'), name="Skole/bhg/idrett")
        if not helse.empty:
            karthelse = helse.explore(m=kartpunkt, style_kwds=dict(color='red'), name="Helse")
        if not brann.empty:
            kartbrann = brann.explore(m=kartpunkt, style_kwds=dict(color='red'), name="Brann/politi")
        if not boliger.empty:
            kart2 = boliger.explore(m=kartpunkt, style_kwds=dict(color='orange'), name="Boliger")

        folium.LayerControl().add_to(kart2)
        st_kart = st_folium(kart2,width=672,zoom=13)
          
    else:
        output_csv = pd.DataFrame()
        st.write('Ingen bygninger eksponert :sunglasses:')
        # =============================================================================
        # kart uten utsatte objekter
        # =============================================================================
        kartQDsyk = gdf_syk.explore(m=kartpunkt,style_kwds=dict(fill=False,color='red'),name ='QDsyk',control=False)
        kartQDbol = gdf_bolig.explore(m=kartpunkt,style_kwds=dict(fill=False,color='orange'),name ='QDbolig',control=False)
        kartQDvei = gdf_vei.explore(m=kartpunkt,style_kwds=dict(fill=False,color='yellow'),name ='QDvei',control=False)
        st_kart = st_folium(kartpunkt,width=672,zoom=13)
 
# =============================================================================
# Eksportering av data i CSV format
# =============================================================================

@st.cache_data
def convert_df(dinn):
# IMPORTANT: Cache the conversion to prevent computation on every rerun
    return dinn.to_csv().encode('utf-8-sig')
csv = convert_df(output_csv)
st.download_button(
   label="Download data as CSV",
   data=csv,
   file_name='eksponerte_bygg.csv',
   mime='text/csv',
   )
