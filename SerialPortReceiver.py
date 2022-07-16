from asyncio import sleep
from genericpath import exists
import os
from serial import Serial
import time

from xtm1 import XTM1, GcodeSanitizer

allowed_gcodes = {
    b'G0', # Move without firing laser
    b'G1', # Move and fire laser with current power setting
    b'G4', # Pause
    b'G90', # Switch to global/absolute coordinates
    b'G91', # Switch to local/relative coordinates
    #b'G92', # M1 does not understand the set-position gcode
    #b'M03', # M1 crashes when it sees too many M3/M4/M5 gcodes.
    #b'M3',
    #b'M04',
    #b'M4',
    #b'M05',
    #b'M5',
}

# These G-codes can be safely removed from the
rejectable_gcodes = {
    b'G21', # Switch to millimeter units. M1 is always in millimeter mode
    b'M05', # Disable laser module. LightBurn uses G0 for non-laser moves, so disabling serves no purpose.
    b'M5', # See M05
    b'M8', # Start air assist. M1 does not have air assist.
    b'M9', # Stop air assist. M1 does not have air assist.
    b'M114', # Get current position. Emitted by LightBurn when Framing. Not useful because M1 sends no replies to G-code.
    b'G00 G17 G40 G21 G54', # Strange G-code emitted by LightBurn when Framing
}

START_GCODE = b"""
# Set default speed for G0 and G1
G1 F9600
G0 F9600
# Disable all periphery (except air purifyer)
M19 S1
# Disable ranging laser pointer
M18 S0

# Pause before start
G4 P0.1

# Move to work area
G0 Y30
# Activate laser module and set power to 0
M4 S0
# Don't know what this does
M104 X0
"""

END_GCODE = b"""
# Move head to origin
G0 Z0 F3000
G0 X0 Y0 F9600

# Small pause
G4 P0.1
# Disable laser module
M05
# Stop gcode
M6 P1
"""

gcode_dir = 'gcode'
if not exists(gcode_dir):
    os.mkdir(gcode_dir)

def filename(i):
    return f'{gcode_dir}/output-{i:04}.gcode'


m1 = XTM1()
serial = Serial('COM8')

filtered_lines = set()

i = 0
while True:
    first_line = True
    #globalizer = GcodeGlobalizer()
    sanitizer = GcodeSanitizer()
    print("\nWaiting for first gcode line... Stop with Ctrl+C")
    serial.timeout = None # Wait forever for the first line
    gcode: bytes = serial.read_until()
    serial.timeout = 1 # Set a 1 second timeout for following lines to detect end of transmission
    total_lines = 0
    while exists(filename(i)) and os.path.getsize(filename(i)) > 0:
        i += 1 # Find free file name
    with open(filename(i), 'wb') as f:
        print(f'{filename(i)}: starting')
        f.write(START_GCODE.strip() + b'\n\n')
        while True:
            if not first_line:
                gcode = serial.read_until()
            first_line = False
            serial.write(b'ok\n')

            if len(gcode) == 0:
                break # Timeout while receiving commands, assume that file is done
            if b'LASER_CUT_DONE' in gcode: # You can put this into "End G-code" in LightBurn, followed by a newline, to mark the end of the file.
                break # End of transmission
            if gcode.split(maxsplit=1)[0] not in allowed_gcodes:
                filtered_lines.add(gcode)
                continue

            original_gcode = gcode
            gcode = sanitizer.process_line(gcode)
            #global_gcode = globalizer.process_line(gcode.decode('utf-8'))

            if len(gcode.strip()) > 0:
                total_lines += 1
                #f.write(b'; ' + original_gcode) # For debugging
                f.write(gcode)
                #f.write(global_gcode.encode('utf-8'))

        f.write(b'\n' + END_GCODE.strip() + b'\n')
    if total_lines < 2:
        print("Not enough lines, deleting file.")
        os.unlink(filename(i))
    else:
        print(f'Wrote {total_lines} lines to {filename(i)}. Filtered out the following lines:')
        filtered_lines_okay = True
        for line in filtered_lines:
            print(f'  {line.strip().decode("utf-8")}')
            if line.strip() not in rejectable_gcodes and line.split(maxsplit=1)[0] not in rejectable_gcodes:
                print(f'WARNING! Unknown G-code was removed: {line}')
                print('Will not upload this file. Please investigate further.')
                filtered_lines_okay = False
                break
        if filtered_lines_okay:
            while True:
                answer = input(f'Upload {filename(i)} to Lasercutter (y/n/d[elete])? ').lower()
                if answer in ('y', 'n', 'd'): break
            if answer == 'y':
                print('Okay, uploading. Press the blue button on the M1 to execute.')
                m1.upload_gcode(file=filename(i))
            elif answer == 'd' or answer == 'delete':
                print(f'Okay, deleting file {filename(i)}.')
                os.unlink(filename(i))
            else:
                print('Okay, then not.')
