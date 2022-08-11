#!/usr/bin/env python3

import sys
import traceback

from xtm1 import XTM1, GcodeTranslator
from gcode import GcodeFramer
from xtm1_camera import camera_stream, get_undistorted_camera_image
from PIL import Image

translator = GcodeTranslator()

#m1 = XTM1()
m1 = XTM1('192.168.178.125')
actions = {
    '--status': lambda: m1.get_status(),
    '--stop': lambda: m1.stop(),
    '--gcode': lambda: m1.execute_gcode_command(' '.join(sys.argv[2:])),
    '--frame': lambda: m1.upload_gcode(GcodeFramer().calculate_frame_file(sys.argv[2])),
    '--upload': lambda: m1.upload_gcode_file(sys.argv[2]),
    '--upload-z': lambda: m1.upload_gcode_file(sys.argv[2], material_thickness=float(sys.argv[3])),
    '--upload-auto': lambda: m1.upload_gcode_file(sys.argv[2], material_thickness='auto'),
    '--translate': lambda: translator.translate_file(sys.argv[2]),
    '--laserpointer': lambda: m1.set_laserpointer(sys.argv[2].lower() == 'on'),
    '--thickness': lambda: m1.measure_thickness(),
    '--light': lambda: m1.set_light_brightness(sys.argv[2]),
    '--camera': lambda: get_undistorted_camera_image(m1, (4000,3000)).save('camera.jpg') or 'wrote camera.jpg',
    '--camera-raw': lambda: open('camera-raw.jpg', 'wb').write(m1.get_camera_image()),
    '--camera-stream': lambda: camera_stream(m1, m1.get_camera_calibration()),
    '--camera-stream-raw': lambda: camera_stream(m1),
}

try:
    action = actions[sys.argv[1]]
except KeyError:
    print(f'Unknown option {sys.argv[1]}', file=sys.stderr)
    for option in actions.keys(): print(option)
    sys.exit(1)
except IndexError:
    print('Supported options: ')
    for option in actions.keys(): print(option)
    sys.exit(2)

try:
    print(action())
except IndexError as ex:
    print(f'\nOption {sys.argv[1]} needs an argument. Please look at the code.\n\n')
    traceback.print_exception(type(ex), ex, ex.__traceback__)
    sys.exit(3)
