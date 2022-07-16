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
        return json.loads(reply)['measure']

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

    def upload_gcode(self, file=None, gcode=None, tool_type='Laser'):
        if not self.is_idle():
            return False
        self.set_tool_type(tool_type)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_STORED, False) as zip_file:
            if file is not None:
                zip_file.write(file, 'gcodes.txt')
            elif gcode is not None:
                zip_file.writestr('gcodes.txt', gcode)
            else:
                raise RuntimeError('You must provide either the file or the gcode argument')
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



class GcodeSanitizer():
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
    def __init__(self) -> None:
        self.material_height_zero_z = 17.0 # Actual Z coordinate for a material thickness of 0
        self.lowest_z_height = 20.0 # This is to prevent crashing the blade into the bed
        self.s_regex = re.compile(b'(S[0-9]*)\.[0-9]+')
        self.z_regex = re.compile(b'^(G0?[0123].*Z)([-0-9]*(\.[0-9]+)?)(.*)$')

    @staticmethod
    def s_replace(match):
        "Remove all fractional decimal places from laser power G1 Snnn parameters."
        return match.group(1)

    def z_replace(self, match):
        "Invert the Z axis direction and apply the focus distance offset."
        start, z, _decimal, rest = match.groups()
        new_z = self.material_height_zero_z - float(z)
        if new_z < 0 or new_z > self.lowest_z_height: # Protect the machine from erroneous calculations
            raise RuntimeError(f'Z={new_z} outside of allowed range [0...{self.lowest_z_height}]. Original G-code was {match.group(0)}')
        return start + str(new_z).encode('utf-8') + rest

    def process_line(self, line):
        # Lightburn can emit fractional laser power values like S123.4, which confuses the M1 firmware.
        line = self.s_regex.sub(GcodeSanitizer.s_replace, line)
        # Lightburn has no way to set an offset for material thickness, so we add that offset here.
        line = self.z_regex.sub(self.z_replace, line)
        # Lightburn sometimes emits move commands with a feed rate of zero. This hangs the M1 firmware.
        line = line.replace(b' F0', b' F9600')
        # Lightburn emits gcodes like G1 X0.1 I S100, but the I confuses the M1.
        line = line.replace(b' I ', b' ')
        return line

    process_file = process_line



class GcodeGlobalizer():
    """Can transform local coordinate to global coordinates in gcode.

    This class was written as a test during debugging, because it was thought
    that the M1 crashed due to too many relative moves. However, the cause was
    different (too many M03/M05 commands).

    The code remains here for now, just in case it is useful in the future.
    """
    def __init__(self) -> None:
        #self.scale = 0
        self.is_relative_mode = False
        self.X = 0
        self.Y = 0
        self.Z = 0
        self.S = 0
        self.globalize_gcodes = ('G0', 'G1', 'G2', 'G3', 'G00', 'G01', 'G02', 'G03')
        self.regex = re.compile('(X|Y|Z)[-0-9\.]+')

    def local_to_global(self, match) -> str:
        snippet = match.group(0)
        if snippet[0] == 'X':
            self.X += float(snippet[1:])
            return snippet[0] + str(self.X)
        elif snippet[0] == 'Y':
            self.Y += float(snippet[1:])
            return snippet[0] + str(self.Y)
        elif snippet[0] == 'Z':
            self.Z -= float(snippet[1:])
            return snippet[0] + str(self.Z)
        else:
            return snippet

    def handle_global_gcode(self, match) -> None:
        snippet = match.group(0)
        if snippet[0] == 'X':
            self.X = float(snippet[1:])
        elif snippet[0] == 'Y':
            self.Y = float(snippet[1:])
        elif snippet[0] == 'Z':
            self.Z = float(snippet[1:])
        #return snippet

    def process_line(self, line: str) -> str:
        comment_split = line.split(';')
        code = comment_split[0] # discard everything after semicolon if it exists
        if 'G91' in code:
            self.is_relative_mode = True
            return '' # Drop all G91 gcodes
        if 'G90' in code:
            self.is_relative_mode = False
            return line
        if code.split(maxsplit=1)[0] in self.globalize_gcodes:
            if self.is_relative_mode:
                comment_split[0] = self.regex.sub(self.local_to_global, code)
            else:
                #comment_split[0] = self.regex.sub(self.handle_global_gcode, code)
                for match in self.regex.finditer(code):
                    self.handle_global_gcode(match)
        return ';'.join(comment_split)

if __name__ == '__main__':
    m1 = XTM1()
    print(m1.get_status())