# -*- coding: utf-8 -*-
"""
Created on Wed Aug  6 09:13:21 2025

@author: KRHE
"""

from shapely import wkt
from datetime import datetime

def extract_coords(geometry_str):
    try:
        point = wkt.loads(geometry_str)
        return point.x, point.y
    except:
        return None, None
    
def format_amrisk_coord(value):
    """Format coordinate with 8 decimals and 3-digit exponent."""
    return f"{value:.8E}".replace("E+0", "E+00").replace("E+1", "E+01").replace("E+2", "E+02")

def calculate_charge_data(q_kg):
    """
    Given Q in kg, returns a formatted string of 3 values for 'Charge data in mag':
    - Q * 1.1 in tons
    - Q in tons
    - P = A + B * Q
    """
    q_ton = q_kg / 1000
    q_with_debris = q_ton * 1.1
    P = 1.5e-4 + 1.5e-10 * q_kg

    return "     ".join([
        format_amrisk_coord(q_with_debris),
        format_amrisk_coord(q_ton),
        format_amrisk_coord(P)
    ])

def generate_amrisk_base_file(coord_x, coord_y, charge_kg, storage_name="Tanogs Export"):
    mag_x = format_amrisk_coord(coord_x)
    mag_y = format_amrisk_coord(coord_y)
    charge_data_fmt = calculate_charge_data(charge_kg)
    now = datetime.now()

    return f"""\
 Flilename                      Exported from AMRISK 2.5
 Storage area name              {storage_name}
 Storage area number            
 Save date                      {now.isoformat()}
 Classification                 NO
 User name                      
 User reference                 
 Global coordinates   0.00000000E+00 0.00000000E+00
 Number of magazines  1
Magazin name          1           Magazine 1
 Magazine type                  FS
 Ammunition type                   
 Remarks on mag                 BNS 20 fot          
 Length of mag        6.05800000E+000
 Width of mag         2.43800000E+000
 Height of mag        2.59100000E+000
 Cross section        6.31685800E+000
 Magazine debris mas  4.80000000E+000
 Magazine volume      3.82675258E+001
 Cover depth          0.00000000E+000
 Front thickness      0.00000000E+00
 Back  thickness      0.00000000E+00
 Roof thickness       0.00000000E+00
 Wall thickness       0.00000000E+00
 Density              0.00000000E+00
 Chamber lining                    
Coordinates x, y         {mag_x}     {mag_y}     0.00000000E+000
Altitude & velocity      0.00000000E+000     0.00000000E+000
Magazin direction        0.00000000E+000     0.00000000E+000
Crater coordinats       0.0000000000E+00    0.0000000000E+00    0.0000000000E+00
Crater 2nd point        0.0000000000E+00    0.0000000000E+00    0.0000000000E+00
Block volume, b-area    0.0000000000E+00    0.0000000000E+00
close dist,by-pass,t    0.0000000000E+00    0.0000000000E+00    0.0000000000E+00
 Tunnel data          0
Number of charges     1  1
Charge data in mag    1     {charge_data_fmt}
Probability calcul              U 11
Remarks on charge   
 Charge = chg ind r 
 Defined situations   4
Defined situations       3.75000000E-001 Night        N O
Defined situations       2.97600000E-001 Day          D O
Defined situations       1.48800000E-001 Evening      E O
Defined situations       1.78600000E-001 Weekend      W O
"""

def generate_exposed_objects(df):
    object_lines = []
    object_lines.append(f" Exposed objects       {len(df)}")

    for idx, row in df.iterrows():
        x, y = extract_coords(row["geometry"])
        x_fmt = format_amrisk_coord(x)
        y_fmt = format_amrisk_coord(y)
        object_name = str(row["Navn"]).replace(" ", "_").replace(",", "_")[:50]

        object_lines.extend([
            f"Object name            {idx+1}  {object_name} Exposed object ",
            " Object ,person type            BNPF           NI                  ",
            " Number of persons       2.11000000E+000",
            " Max precence            9.00000000E-001",
            " Width of area           0.00000000E+000",
            " Length of train         0.00000000E+000",
            " Number trains/week      0.00000000E+000",
            " Velocity of object      0.00000000E+000",
            " Remarks on object",
            " Nr object points     1",
            f"Object points       NDNF   {x_fmt}     {y_fmt}     0.00000000E+000",
            " Average precense               N 0.00000000E+000",
            " Average precense               D 0.00000000E+000",
            " Average precense               E 0.00000000E+000",
            " Average precense               W 0.00000000E+000",
        ])
    return "\n".join(object_lines)