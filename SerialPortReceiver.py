from asyncio import sleep
from genericpath import exists
import os
from serial import Serial
import time

from xtm1 import XTM1
from xtm1 import GcodeGlobalizer

allowed_gcodes = {
    b'G0',
    b'G1',
    b'G4',
    b'G90',
    b'G91',
    #b'G92', # M1 does not understand the set-position gcode
    #b'M03', # M1 crashes when it sees too many M3/M4/M5 gcodes.
    #b'M3',
    #b'M04',
    #b'M4',
    #b'M05',
    #b'M5',
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

def read_line(self, timeout=None):
    self.timeout = timeout
    return self.read_until()
Serial.read_line = read_line

m1 = XTM1()
serial = Serial('COM8')

filtered_lines = set()

i = 0
while True:
    first_line = True
    globalizer = GcodeGlobalizer()
    print("\nWaiting for first gcode line...")
    gcode: bytes = serial.read_line()
    total_lines = 0
    while exists(filename(i)) and os.path.getsize(filename(i)) > 0:
        i += 1 # Find free file name
    with open(filename(i), 'wb') as f:
        print(f'{filename(i)}: starting')
        f.write(START_GCODE.strip() + b'\n\n')
        while True:
            if not first_line:
                gcode = serial.read_line(timeout=1)
            first_line = False
            serial.write(b'ok\n')

            if len(gcode.strip()) == 0:
                break # Timeout while receiving commands, assume that file is done
            if b'LASER_CUT_DONE' in gcode:
                break # End of transmission
            if gcode.split(maxsplit=1)[0] not in allowed_gcodes:
                filtered_lines.add(gcode)
                continue

            #global_gcode = globalizer.process_line(gcode.decode('utf-8'))

            if len(gcode) > 0:
                total_lines += 1
                #print(global_gcode)
                f.write(gcode)
                #f.write(b'; ' + gcode) # For debugging
                #f.write(global_gcode.encode('utf-8'))

        f.write(END_GCODE.strip() + b'\n')
    if total_lines < 2:
        print("Not enough lines, deleting file.")
        os.unlink(filename(i))
    else:
        print(f'Wrote {total_lines} lines to {filename(i)}. Filtered out the following lines:')
        for line in filtered_lines:
            print(f'  {line.strip().decode("utf-8")}')
        while True:
            answer = input('Upload file to Lasercutter (y/n)? ').lower()
            if answer in ('y', 'n'): break
        if answer == 'y':
            m1.upload_gcode(file=filename(i))
