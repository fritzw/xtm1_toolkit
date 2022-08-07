#!/usr/bin/env python3

import argparse
import os
import socket
import subprocess as subp
import sys
from textwrap import dedent

from serial import Serial

from StreamLineReader import StreamLineReader
from xtm1 import XTM1, GcodeTranslator, UnexpectedGcodeError

TIMEOUT_SECONDS = 1

parser = argparse.ArgumentParser(
    description=dedent('''
        Receive G-code from LightBurn, convert it to a format understood by the laser cutter, and then upload it to the laser cutter.
        '''),    
    epilog=dedent('''
        One of the options --watch, --tcp or --serial is required to determine how G-code should be received.
        Also, either of --usb or --ip is required to specify how to connect to the laser cutter.
        ''')
)

def positive_integer(s: str) -> int:
    i = int(s)
    if i < 0: raise ValueError()
    return i

input_args = parser.add_mutually_exclusive_group(required=True)
input_args.add_argument('--watch', '-w', nargs=1, metavar='DIR',
    help='Watch directory DIR for new G-code files to upload to laser cutter.')
streaming_args = input_args.add_mutually_exclusive_group(required=False)
streaming_args.add_argument('--tcp', '-t', type=positive_integer, metavar='PORT', nargs='?', const=2323,
    help='Listen for grbl-TCP connection from LightBurn on port PORT (default = 2323). PORT==0 will use tcp_bridge.')
streaming_args.add_argument('--serial', '-s', nargs=1, metavar='PORT',
    help='Open the serial port PORT. Most likely this should be one port of a virtual serial port pair like com0com or tty0tty.')

target_device_args = parser.add_mutually_exclusive_group(required=True)
target_device_args.add_argument('--ip',
    help='IP address of the laser cutter device.')
target_device_args.add_argument('--usb', action='store_const', dest='ip', const='201.234.3.1',
    help='Connect to laser cutter via USB (which is a network interface with IP 201.234.3.1).')

ARGS = parser.parse_args()


stream = None
if ARGS.tcp == 0: # --tcp==0 means 'use tcp_bridge'
    tcp_process = subp.Popen('tcp_bridge/tcp_bridge', stdin=subp.PIPE, stdout=subp.PIPE)
    stream = StreamLineReader(tcp_process)
elif ARGS.tcp: # --tcp was given with a positive port number
    port = ARGS.tcp
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', port))
    print(f'Waiting for TCP connection on port {port}...')
    sock.listen(1)
    client_connection, _client_ddr = sock.accept()
    stream = StreamLineReader(client_connection)
elif ARGS.serial:
    serial = Serial(ARGS.serial)
    stream = StreamLineReader(serial)
elif ARGS.watch:
    print('Sorry, --watch is not implemeted yet.')
    sys.exit(1)

assert stream
assert ARGS.ip

gcode_dir = 'gcode'
if not os.path.exists(gcode_dir):
    os.mkdir(gcode_dir)

def filename(i):
    return f'{gcode_dir}/output-{i:04}.gcode'


m1 = XTM1(ARGS.ip)

i = 0

def receive_gcode_transmission():
    global i
    print("\nWaiting for LASER_JOB_START... Stop with Ctrl+C")
    line: bytes = stream.readline() # Wait forever for the first line
    stream.write_flush(b'ok\n')
    while not b'LASER_JOB_START' in line:
        print(f'Received G-code {line.strip()} ... skipping')
        # TODO: Check G-code line and possibly execute on machine immediately?
        line = stream.readline() # Wait forever for the first line
        stream.write_flush(b'ok\n')

    while os.path.exists(filename(i)) and (not os.path.isfile(filename(i))
                                            or os.path.getsize(filename(i)) > 0):
        i += 1 # Skip all names which exist and are either non-empty or not normal files
    total_lines = 0
    with open(filename(i), 'wb') as f:
        print(f'{filename(i)}: starting')
        while True:
            line = stream.readline(timeout=TIMEOUT_SECONDS)
            stream.write(b'ok\n')
            #print(line)

            if len(line) == 0:
                break # Timeout while receiving commands, assume that file is done
            if b'LASER_JOB_END' in line: # You can put this into "End G-code" in LightBurn, followed by a newline, to mark the end of the file.
                break # End of transmission

            total_lines += 1
            f.write(line)

    if total_lines < 4: # Filter out bogus files
        print("Not enough lines, deleting file.")
        os.unlink(filename(i))
        return # On to the next file

    print(f'Wrote {total_lines} lines to {filename(i)}. Now converting...')
    translator = GcodeTranslator()
    try:
        translated_file = translator.translate_file(filename(i))
    except UnexpectedGcodeError as e:
        print(e.args[0])
        return
    
    print(f'Preparing to upload {translated_file} to laser cutter...')
    print('Please enter material thickness in millimeters (or none/auto/cancel/delete).')
    print('  "none" will not modify the Z height in the G-code.')
    print('  "auto" will measure the appropriate Z height using the red laser pointer.')
    print('  "cancel" will leave this file and wait to receive the next file.')
    print('  "delete" will delete this file and wait to receive the next file.')
    answer = ''
    while answer == '':
        answer = input(f'Enter thickness or n/a/c/d: ').lower()
        if 'cancel' in answer or answer == 'c':
            answer = 'cancel'
        elif 'delete' in answer or answer == 'd':
            answer = 'delete'
        elif 'none' in answer or answer == 'n':
            thickness = None
        elif 'auto' in answer or answer == 'a':
            thickness = 'auto'
        else:
            try:
                thickness = float(answer)
            except ValueError:
                print(f'Did not understand value: {answer}, please try again')
                answer = '' # Repeat while loop
    if answer == 'delete':
        print(f'Okay, deleting 2 files {filename(i)} and {translated_file}.')
        os.unlink(filename(i))
        os.unlink(translated_file)
    elif answer == 'cancel':
        print(f'Okay, not uploading {translated_file}.')
    else:
        print('Okay, uploading {translated_file}.')
        if (thickness == 'auto'):
            print('Auto-measuring material thickness might take a while.')
        print('Press the button on the M1 when it lights blue to execute the file.')
        m1.upload_gcode_file(translated_file, material_thickness=thickness)

try:
    while True:
        receive_gcode_transmission()
except KeyboardInterrupt:
    print('\nShutting down because of keyboard interrupt.')
    sys.exit(0)
