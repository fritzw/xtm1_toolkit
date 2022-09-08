import io
import json
import os
import tkinter as tk
from queue import Queue
from threading import Thread
from time import sleep, time

import cv2
import numpy as np
from PIL import Image, ImageTk
from scipy import interpolate

from xtm1 import XTM1


def undistort(img, calibration_points, target_size) -> Image.Image:
    w, h = target_size
    xs = np.linspace(0, 40, w, dtype='float32')
    ys = np.linspace(0, 30, h, dtype='float32')
    sample_xy = [[[x,y] for x in xs] for y in ys]
    grid_x, grid_y = np.arange(41), np.arange(31)
    distorted = np.array([[[p['x'], p['y']] for p in row] for row in calibration_points])
    distorted = np.swapaxes(distorted, 0, 1)
    x_inter = interpolate.interpn((grid_x, grid_y), distorted, sample_xy)
    x_inter = np.asarray(x_inter, dtype='float32')
    img2 = cv2.remap(np.asarray(img), x_inter, None, cv2.INTER_CUBIC)
    return Image.fromarray(img2)


def get_undistorted_camera_image(m1: XTM1, size) -> Image.Image:
    img = Image.open(io.BytesIO(m1.get_camera_image()))
    points = load_calibration_data(m1)
    undistorted = undistort(img, points, size)
    return undistorted


def load_calibration_data(m1: XTM1) -> list:
    try:
        with open('camera-calibration.json', 'rb') as f:
            data = f.read()
    except IOError:
        data = m1.get_camera_calibration()
        with open('camera-calibration.json', 'wb') as f:
            f.write(data)
    json_obj = json.loads(data)
    return json_obj['points']



def camera_stream(m1: XTM1, calibration_str=None, size=(1164, 874)):
    points = load_calibration_data(m1)
    root = tk.Tk()
    canvas = tk.Canvas(root, width = size[0], height = size[1])
    canvas.pack()
    image_id = None
    image = None
    image_queue = Queue(1)
    done = False
    frame_i = 0
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
                if calibration_str:
                    img = undistort(img, points, size)
                    image_queue.put(img)
                else:
                    image_queue.put(img.resize(size))
    get_image_thread: Thread = Thread(target=get_image)
    get_image_thread.start()
    start_time = time()
    def update_image():
        nonlocal image_id, image, frame_i
        if not image_queue.empty():
            image = ImageTk.PhotoImage(image_queue.get())
            if image_id is not None: canvas.delete(image_id)
            image_id = canvas.create_image(0, 0, anchor=tk.NW, image=image)
            frame_i += 1
            fps = frame_i / (time() - start_time)
            root.title(f'Camera, {fps:0.2f} FPS, Frame {frame_i}')
        root.after(20, update_image)
    root.after(100, update_image)
    root.mainloop()
    done = True
    get_image_thread.join()
    return 'Camera stream stopped'

