# xTool M1 Toolkit

This project contains tools to control the xTool M1 laser cutter / blade cutter.
The initial aim is to use LightBurn for laser cutting with the M1, so the current focus is on laser cutting only, not blade cutting.

> ***This is an unofficial project. It is not affiliated with xTool or LightBurn. It might break your machine. No warranties, use at your own risk.***

## m1control.py

This script can send commands and upload G-code files to the xTool M1.
Currently supported commands are:

```
--status:
    Get current status,
--stop:
    Stop current job,
--gcode GCODE:
    DANGER! Execute the given GCODE line on the laser cutter. DANGER!
--upload filename.gcode:
    Upload the given G-code file to connected M1
--thickness:
    Measure the current material thickness using the red laser pinter
--laserpointer on|off:
    Turn the red laser pointer on or off (not really useful)
--light:
    Set the box light brightness (0-255)
--camera:
    Save the current camera view as camera.jpg
--camera-calibration:
    Save the camera calibration coefficients (I guess) as camera-calibration.json
```

## SerialPortReceiver.py

This script will open a serial port, receive G-code lines, convert them to a format compatible with the M1 firmware, and write them to a file.
The file can then be uploaded to a connected M1 machine, where it can be executed by pressing the button (like normal).
In order to use this, you probably want to use a virtual serial port like http://com0com.sourceforge.net/ and connect one end to LightBurn and the other to this script.

This is necessary for camera calibration (and framing) because LightBurn will not let you save the G-code file for the camera calibration pattern.
LightBurn will only send the G-code directly to a laser cutter connected via serial port, which does not work because the M1 does not provide a serial port (it registers as a USB network interface).
This script talks to LightBurn, receives the G-code, and uploads it to the M1.

## xtm1.py

This library contains the code to communicate with the xTool M1, as well as some machine-specific G-code filters.
