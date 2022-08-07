#!/usr/bin/env python3

import argparse
import os
import subprocess as subp

from serial import Serial

from StreamLineReader import StreamLineReader
from xtm1 import XTM1, GcodeTranslator

parser = argparse.ArgumentParser()

input_args = parser.add_mutually_exclusive_group(required=True)
input_args.add_argument('--watch', '-w', nargs=1, metavar='DIR',
    help='Watch directory DIR for new G-code files to upload to laser cutter.')
streaming_args = input_args.add_mutually_exclusive_group(required=False)
streaming_args.add_argument('--tcp', '-t', action='store_true',
    help='Listen for grbl-TCP connection from LightBurn on port 23')
streaming_args.add_argument('--serial', '-s', nargs=1, metavar='PORT',
    help='Open the serial port PORT. Most likely this should be one port of a virtual serial port pair like com0com or tty0tty.')

target_device_args = parser.add_mutually_exclusive_group(required=True)
target_device_args.add_argument('--ip',
    help='IP address of the laser cutter device.')
target_device_args.add_argument('--usb', action='store_const', dest='ip', const='201.234.3.1',
    help='Connect to laser cutter via USB (which is a network interface with IP 201.234.3.1).')

ARGS = parser.parse_args()


stream = None
if ARGS.tcp:
    tcp_process = subp.Popen('tcp_bridge/tcp_bridge', stdin=subp.PIPE, stdout=subp.PIPE)
    stream = StreamLineReader(tcp_process)
elif ARGS.serial:
    serial = Serial(ARGS.serial)
    stream = StreamLineReader(serial)

assert stream
assert ARGS.ip

gcode_dir = 'gcode'
if not os.path.exists(gcode_dir):
    os.mkdir(gcode_dir)

def filename(i):
    return f'{gcode_dir}/output-{i:04}.gcode'


m1 = XTM1(ARGS.ip)


filtered_lines = set()
timeout_seconds = 1

i = 0
while True:
    is_first_line = True
    print("\nWaiting for first gcode line... Stop with Ctrl+C")
    line: bytes = stream.readline() # Wait forever for the first line
    total_lines = 0
    while os.path.exists(filename(i)) and (not os.path.isfile(filename(i))
                                            or os.path.getsize(filename(i)) > 0):
        i += 1 # Skip all names which exist and are either non-empty or not normal files
    with open(filename(i), 'wb') as f:
        print(f'{filename(i)}: starting')
        while True:
            if not is_first_line:
                line = stream.readline(timeout=timeout_seconds)
            print(line)
            is_first_line = False
            stream.write(b'ok\n')

            if len(line) == 0:
                break # Timeout while receiving commands, assume that file is done
            if b'LASER_CUT_DONE' in line: # You can put this into "End G-code" in LightBurn, followed by a newline, to mark the end of the file.
                break # End of transmission
            original_gcode = line
            #line = sanitizer.process_line(line)
            #global_gcode = globalizer.process_line(line.decode('utf-8'))

            total_lines += 1
            f.write(line)

    if total_lines < 4:
        print("Not enough lines, deleting file.")
        os.unlink(filename(i))
        continue # On to the next file

    print(f'Wrote {total_lines} lines to {filename(i)}. Now converting...')
    translator = GcodeTranslator()
    try:
        translated_file = translator.translate_file(filename(i))
    except GcodeTranslator.UnexpectedGcodeError as e:
        print(e.args[0])
        continue
    
    answer = ''
    while answer not in ('y', 'n', 'd', 'delete'):
        answer = input(f'Upload {translated_file} to Lasercutter (y/n/d[elete])? ').lower()
    if answer == 'y':
        print('Okay, uploading. Press the blue button on the M1 to execute.')
        m1.upload_gcode_file(filename=translated_file)
    elif answer == 'd' or answer == 'delete':
        print(f'Okay, deleting 2 files {filename(i)} and {translated_file}.')
        os.unlink(filename(i))
        os.unlink(translated_file)
    else:
        print('Not uploading {translated_file}.')
