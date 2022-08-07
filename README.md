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
    DANGER! Immediately execute the given GCODE line on the laser cutter. DANGER!
--upload filename.gcode:
    Translate and upload the given G-code file to connected M1
--upload-z filename.gcode thickness:
    Translate and upload the given G-code file to connected M1.
    Modify the Z height in the file for the given material thickness
    (thickness should be set to 0 in LightBurn)
--upload-auto filename.gcode:
    Translate and upload the given G-code file to connected M1.
    Measure material thickness and modify the Z height in the file accordingly
    (thickness should be set to 0 in LightBurn)
--translate filename.gcode:
    Translate the given G-code file to connected M1 but do not upload.
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

## LightBurnAdapter.py

This script will open a (virtual) serial port or a TCP port, receive G-code lines from LightBurn, convert them to a format compatible with the M1 firmware, and write them to a file.
The file can then be uploaded to a connected M1 machine, where it can be executed by pressing the button (like normal).
In order to use this, you probably want to use a virtual serial port like http://com0com.sourceforge.net/ and connect one end to LightBurn and the other to this script.

This is necessary for camera calibration (and framing) because LightBurn will not let you save the G-code file for the camera calibration pattern.
LightBurn will only send the G-code directly to a laser cutter connected via serial port, which does not work because the M1 does not provide a serial port (it registers as a USB network interface).
This script talks to LightBurn, receives the G-code, and uploads it to the M1.

### tcp_bridge
If you want to listen on a TCP port below 1024 (default in LightBurn is 23) you need root privileges on Linux. Since running python scripts as root is a bad idea, the small C program `tcp_bridge` does nothing but opening a TCP port and passing data to the python script.

Run `make PORT=n` to compile the program for listening on a specific port `n`.
The resulting program `tcp_bridge` can then be given rights for the specific operation of opening ports by running `make setcap`.

## xtm1.py

This library contains the code to communicate with the xTool M1, as well as some machine-specific G-code filters.
