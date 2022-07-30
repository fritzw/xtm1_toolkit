from genericpath import exists
import io
import requests
import zipfile
import json
import time
import re

class XTM1:
    def __init__(self, IP='201.234.3.1') -> None:
        self.IP = IP
        self.PORT = 8080
        self.CAMERA_PORT = 8329

    def get_status(self) -> dict:
        reply = self._get_request(f'/cnc/status').decode('utf-8')
        return json.loads(reply)

    def is_idle(self) -> bool:
        status = self.get_status()
        return status['STATUS'] in ('P_IDLE', 'P_SLEEP', 'P_FINISH')

    def stop(self):
        return self._get_request('/cnc/data?action=stop')

    def set_laserpointer(self, on: bool):
        return self.execute_gcode_command('M18 S255' if on else 'M18 S0')

    def measure_thickness(self) -> float:
        reply = self._get_request('/camera?focus=9007199254740991,9007199254740991,0,0', port=self.CAMERA_PORT)
        return float(json.loads(reply)['measure'])

    def get_camera_image(self) -> bytes:
        return self._get_request('/snap?stream=0', port=self.CAMERA_PORT)

    def get_camera_calibration(self) -> bytes:
        return self._get_request('/file?action=download&filename=points.json')

    def set_light_brightness(self, brightness):
        brightness = max(0, min(int(brightness), 255))
        return self.execute_gcode_command(f'M13 S{brightness}')

    def execute_gcode_command(self, gcode):
        timestamp = int(time.time() * 1000)
        gcode = gcode.replace(' ', '%20')
        return self._get_request(f'/cnc/cmd?cmd={gcode}&t={timestamp}')
    
    def upload_gcode_file(self, filename, material_thickness=None):
        with open(filename, 'rb') as f:
            return self.upload_gcode(f.read(), material_thickness=material_thickness)

    def upload_gcode(self, gcode, material_thickness=None, tool_type='Laser'):
        if not self.is_idle():
            return False
        if tool_type != 'Laser':
            raise NotImplementedError('Only Laser G-code is currently supported, not ' + tool_type)
        self.set_tool_type(tool_type)

        translator = GcodeTranslator()
        if material_thickness == 'auto':
            print('Measuring material thicknes... ', end='')
            material_thickness = self.measure_thickness()
            print(material_thickness)
            translator.force_material_thickness = material_thickness
        elif material_thickness is not None:
            translator.force_material_thickness = material_thickness
        else:
            pass # Use the Z values present in G-code file, just invert them
            
        gcode = translator.translate_file_content(gcode)
        #print('################ G-Code file contents: ###########')
        #print(gcode.decode('utf-8'))

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_STORED, False) as zip_file:
            zip_file.writestr('gcodes.txt', gcode)
        zip_buffer.seek(0)
        return self._post_request('/cnc/data?action=upload&zip=true&id=-1', data=zip_buffer)

    def set_tool_type(self, type='Laser'):
        return self._post_request('/setprintToolType?type=' + type)

    def _post_request(self, url, port=None, **kwargs) -> bytes:
        headers = { 'Content-Type': 'application/x-www-form-urlencoded' }
        if port is None: port = self.PORT
        full_url = f'http://{self.IP}:{port}{url}'
        result = requests.post(full_url, headers=headers, timeout=10, **kwargs)
        if result.status_code != 200:
            raise RuntimeError(f'Device returned HTTP status {result.status_code} for POST {full_url}')
        return result.content

    def _get_request(self, url, port=None, **kwargs) -> bytes:
        if port is None: port = self.PORT
        full_url = f'http://{self.IP}:{port}{url}'
        result = requests.get(full_url, timeout=10, **kwargs)
        if result.status_code != 200:
            raise RuntimeError(f'Device returned HTTP status {result.status_code} for GET {full_url}')
        return result.content


import re

_whitespace_only_re = re.compile(rb'^[ \t]+$', re.MULTILINE)
_leading_whitespace_re = re.compile(rb'(^[ \t]*)(?:[^ \t\n])', re.MULTILINE)

def dedent_bytes(text):
    """Remove any common leading whitespace from every line in `text`.

    This can be used to make triple-quoted strings line up with the left
    edge of the display, while still presenting them in the source code
    in indented form.

    Note that tabs and spaces are both treated as whitespace, but they
    are not equal: the lines "  hello" and "\\thello" are
    considered to have no common leading whitespace.  (This behaviour is
    new in Python 2.5; older versions of this module incorrectly
    expanded tabs before searching for common leading whitespace.)
    """
    # Look for the longest leading string of spaces and tabs common to
    # all lines.
    margin = None
    text = _whitespace_only_re.sub(b'', text)
    indents = _leading_whitespace_re.findall(text)
    for indent in indents:
        if margin is None:
            margin = indent

        # Current line more deeply indented than previous winner:
        # no change (previous winner is still on top).
        elif indent.startswith(margin):
            pass

        # Current line consistent with and no deeper than previous winner:
        # it's the new winner.
        elif margin.startswith(indent):
            margin = indent

        # Find the largest common whitespace between current line
        # and previous winner.
        else:
            for i, (x, y) in enumerate(zip(margin, indent)):
                if x != y:
                    margin = margin[:i]
                    break
            else:
                margin = margin[:len(indent)]

    # sanity check (testing/debugging only)
    if 0 and margin:
        for line in text.split(b"\n"):
            assert not line or line.startswith(margin), \
                   "line = %r, margin = %r" % (line, margin)

    if margin:
        text = re.sub(rb'(?m)^' + margin, b'', text)
    return text

class GcodeTranslator():
    """Translates LightBurn's Marlin G-code into a format understood by the M1.

    Lightburn emits some G-code commands which are probably understood by Marlin
    but confuse the M1. So we need to remove these confusion features in order
    to execute the G-code on the M1.

    Additionally, all Z coordinates in move commands will be inverted and subtracted
    from self.material_height_zero_z. This is because the positive Z direction points
    down in the M1, and the Z height for correct focus for material thickness zero is
    Z=17. This way, setting the material thickness in LightBurn will be translated into
    the correct Z movement for the M1.
    """

    class UnexpectedGcodeError(Exception): ...

    START_GCODE = dedent_bytes(b"""
    ;XTM1_HEADER_START;
    ; Set default speed for G0 and G1
    G1 F9600
    G0 F9600
    ; Disable all periphery (except air purifyer)
    M19 S1
    ; Disable ranging laser pointer
    M18 S0

    ; Pause before start
    G4 P0.1

    ; Move to work area
    G0 Y30
    ; Activate laser module and set power to 0
    M4 S0
    ; Don't know what this does
    M104 X0
    ;XTM1_HEADER_END;

    """)

    END_GCODE = dedent_bytes(b"""

    ;XTM1_FOOTER_START;
    ; Move head to origin
    G0 Z0 F3000
    G0 X0 Y0 F9600

    ; Small pause
    G4 P0.1
    ; Disable laser module
    M05
    ; Stop gcode
    M6 P1
    ;XTM1_FOOTER_END;
    """)

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

    # These G-codes can be safely removed from the file
    rejectable_gcodes = {
        b'G21', # Switch to millimeter units. M1 is always in millimeter mode
        b'M05',b'M5', # Disable laser module. LightBurn uses G1/S0 or G0 for non-laser moves, so disabling serves no purpose.
        b'M4',b'M04', b'M3', b'M03', # Enabling the laser module serves no purpose because it should always be enabled during a job.
        b'M8', # Start air assist. M1 does not have air assist.
        b'M9', # Stop air assist. M1 does not have air assist.
        b'M114', # Get current position. Emitted by LightBurn when Framing. Not useful because M1 sends no replies to G-code.
        b'G00 G17 G40 G21 G54', # Strange G-code emitted by LightBurn when Framing
        b'LASER_JOB_START', b'LASER_JOB_END', # These are used for Streaming mode by LightBurnAdapter.py
    }


    def __init__(self) -> None:
        self.material_height_zero_z = 17.0 # Actual Z coordinate for a material thickness of 0
        #self.material_height_zero_z = 19.0 # The real focus height seems a bit lower for my M1. Needs further investigation 
        self.lowest_z_height = 35.0 # This is to prevent crashing the blade into the bed
        self.force_material_thickness =  None
        self.s_regex = re.compile(rb'(S[0-9]*)\.[0-9]+')
        self.z_regex = re.compile(rb'^(G0?[0123].*?Z)([-0-9]*(\.[0-9]+)?)(.*?)$')
        self.z_regex_multiline = re.compile(rb'^(G0?[0123].*?Z)([-0-9]*(\.[0-9]+)?)(.*?)$')
        self.filtered_lines = set()

    @staticmethod
    def s_replace(match):
        "Remove all fractional decimal places from laser power G1 Snnn parameters."
        return match.group(1)

    def z_match_invert(self, match):
        "Invert the Z axis direction and apply the focus distance offset."
        start, z, _decimal, rest = match.groups()

        if self.force_material_thickness is not None:
            new_z = self.material_height_zero_z - self.force_material_thickness - float(z)
        else:
            new_z = self.material_height_zero_z - float(z)
        if new_z < 0 or new_z > self.lowest_z_height: # Protect the machine from erroneous calculations
            raise RuntimeError(f'Z={new_z} outside of allowed range [0...{self.lowest_z_height}]. Original G-code was {match.group(0)}')
        return start + str(new_z).encode('utf-8') + rest
    
    def process_line(self, line: bytes) -> bytes:
        line = line.strip()
        command, *comment = line.split(b';', maxsplit=1)
        if len(command.strip()) == 0:
            return line # Only whitespace, pass through unmodified

        command = line.split(maxsplit=1)[0]
        if command not in self.allowed_gcodes:
            if command not in self.rejectable_gcodes and line not in self.rejectable_gcodes:
                raise self.UnexpectedGcodeError(f'Unknown G-code: {line}. Please investigate this situation and decide whether to add it to GcodeTranslator.rejectable_gcodes')
            self.filtered_lines.add(line)
            return b';--' + line # Disallowed line, comment out and mark as filtered

        # Lightburn can emit fractional laser power values like S123.4, which confuses the M1 firmware.
        line = self.s_regex.sub(self.s_replace, line)
        # Lightburn has no way to set an offset for material thickness, so we add that offset here.
        line = self.z_regex.sub(self.z_match_invert, line)
        # Lightburn sometimes emits move commands with a feed rate of zero. This hangs the M1 firmware.
        line = line.replace(b' F0', b' F9600')
        # Lightburn emits gcodes like G1 X0.1 I S100, but the I confuses the M1.
        line = line.replace(b' I ', b' ')
        return line

    def is_already_processed(self, gcode: bytes) -> bool:
        return b'XTM1_HEADER_START' in gcode[0:1024]

    def translate_file_content(self, gcode: bytes) -> bytes:
        if self.is_already_processed(gcode):
            return gcode
        new_lines = [
            self.process_line(line) 
            for line in gcode.split(b'\n')
        ]
        return self.START_GCODE + b'\n'.join(new_lines) + self.END_GCODE

    def translate_file(self, filename: str) -> str:
        parts = filename.split('.')
        parts[-2] = parts[-2] + '.xtm1'
        new_filename = '.'.join(parts)

        with open(filename, 'rb') as f:
            gcode = f.read(1024)
            if self.is_already_processed(gcode):
                return filename
            gcode = gcode + f.read()
        with open(new_filename, 'wb') as f:
            f.write(self.translate_file_content(gcode))
        return new_filename

if __name__ == '__main__':
    m1 = XTM1()
    print(m1.get_status())