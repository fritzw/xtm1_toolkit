#!/usr/bin/env python3

import io
from queue import Queue
import sys
from threading import Thread
from time import sleep
import traceback

import requests
from xtm1 import XTM1, GcodeTranslator
from gcode import GcodeFramer
import tkinter as tk
from PIL import ImageTk, Image


translator = GcodeTranslator()

def camera_stream():
    root = tk.Tk()
    canvas = tk.Canvas(root, width = 1200, height = 800)
    canvas.pack()
    image_id = None
    image = None
    image_queue = Queue(1)
    done = False
    def get_image():
        nonlocal done
        while not done:
            try:
                data = m1.get_camera_image()
            except Exception as e:
                print('Error getting image, waiting 1 second before retrying: ' + str(type(e).__name__))
                sleep(1)
            else:
                img = Image.open(io.BytesIO(data))
                image_queue.put(img.resize((1200,800)))
    get_image_thread: Thread = Thread(target=get_image)
    get_image_thread.start()
    def update_image():
        nonlocal image_id, image
        if image_queue.not_empty:
            image = ImageTk.PhotoImage(image_queue.get())
            if image_id is not None: canvas.delete(image_id)
            image_id = canvas.create_image(0, 0, anchor=tk.NW, image=image)
            canvas.update()
        root.after(100, update_image)
    root.after(100, update_image)
    root.mainloop()
    done = True
    get_image_thread.join()
    return 'Camera stream stopped'

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
    '--camera': lambda: open('camera.jpg', 'wb').write(m1.get_camera_image()),
    '--camera-stream': camera_stream,
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
except IndexError as ex:
    print(f'\nOption {sys.argv[1]} needs an argument. Please look at the code.\n\n')
    traceback.print_exception(type(ex), ex, ex.__traceback__)
    sys.exit(3)
