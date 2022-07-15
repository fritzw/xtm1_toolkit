#!/usr/bin/end python3
import sys
from xtm1 import XTM1

m1 = XTM1()
actions = {
    '--status': lambda: m1.get_status(),
    '--stop': lambda: m1.stop(),
    '--gcode': lambda: m1.execute_gcode_command(' '.join(sys.argv[2:])),
    '--upload': lambda: m1.upload_gcode(file=sys.argv[2]),
    '--laserpointer': lambda: m1.set_laserpointer(sys.argv[2].lower() == 'on'),
    '--thickness': lambda: m1.measure_thickness(),
    '--light': lambda: m1.set_light_brightness(sys.argv[2]),
    '--camera': lambda: open('camera.jpg', 'wb').write(m1.get_camera_image()),
    '--camera-calibration': lambda: open('camera-calibration.json', 'wb').write(m1.get_camera_calibration()),
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
except IndexError:
    print(f'Option {sys.argv[1]} needs an argument. Please look at the code.')
    sys.exit(3)
