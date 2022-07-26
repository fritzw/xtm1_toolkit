from io import UnsupportedOperation
import math
import re
from textwrap import dedent

class GcodeFramer():
    'Analyzes G-code files to determine the area in which the laser is active.'
    def __init__(self) -> None:
        #self.scale = 0
        self.is_relative_mode = False
        self.current_command = b''
        self.X = 0
        self.Y = 0
        self.Z = 0
        self.Xminmax = (1e10, -1e10)
        self.Yminmax = (1e10, -1e10)
        self.S = 0
        self.allowed_gcodes = (b'G0', b'G1', b'G00', b'G01',)
        self.cutting_gcodes = (b'G1', b'G01')
        self.disallowed_gcodes = (b'G2', b'G3', b'G02', b'G03')
        self.regex = re.compile(rb'(X|Y)([-0-9\.]+)')
        self.S_regex = re.compile(rb'S([-0-9\.]*)')
        self.starts_cutting = False
        self.is_cutting = False

    def handle_local_gcode(self, match) -> str:
        letter = match.group(1)
        value = float(match.group(2))
        if letter == b'X':
            self.X += value
            if self.is_cutting: self.update_X(self.X)
        elif letter == b'Y':
            self.Y += value
            if self.is_cutting: self.update_Y(self.Y)

    @staticmethod
    def min_max(old_minmax, new_value):
        oldmin, oldmax = old_minmax
        return min(oldmin, new_value), max(oldmax, new_value)

    def update_X(self, value):
        self.Xminmax = self.min_max(self.Xminmax, value)

    def update_Y(self, value):
        self.Yminmax = self.min_max(self.Yminmax, value)

    def handle_global_gcode(self, match) -> None:
        letter = match.group(1)
        value = float(match.group(2))
        if letter == b'X':
            self.X = value
            if self.is_cutting: self.update_X(self.X)
        elif letter == b'Y':
            self.Y = value
            if self.is_cutting: self.update_Y(self.Y)

    def process_line(self, line: bytes) -> None:
        code = line.split(b';')[0] # Remove comments starting with ;
        code = code.split(b'#')[0] # Remove comments starting with #
        if len(code.strip()) == 0:
            return
        if b'G91' in code:
            self.is_relative_mode = True
            return
        if b'G90' in code:
            self.is_relative_mode = False
            return 
        self.current_command = code.strip().split(maxsplit=1)[0]
        if self.current_command in self.disallowed_gcodes:
            raise RuntimeError('Cannot handle G-code ' + str(self.current_comman.strip()))
        if self.current_command in self.allowed_gcodes:
            if b'S' in code:
                match = self.S_regex.search(code)
                self.S = float(match.group(1))
            if self.current_command in self.cutting_gcodes and self.S > 0:
                self.starts_cutting = not self.is_cutting
                self.is_cutting = True
            else:
                self.starts_cutting = False
                self.is_cutting = False
            if self.starts_cutting:
                self.update_X(self.X)
                self.update_Y(self.Y)

            if self.is_relative_mode:
                for match in self.regex.finditer(code):
                    self.handle_local_gcode(match)
            else:
                for match in self.regex.finditer(code):
                    self.handle_global_gcode(match)

    def calculate_frame(self, gcode: bytes):
        for line in gcode.split(b'\n'):
            self.process_line(line)
        print(self.Xminmax, self.Yminmax)

    def calculate_frame_file(self, filename: str):
        with open(filename, 'rb') as f:
            for line in f.readlines():
                self.process_line(line)
        Xmin, Xmax = self.Xminmax
        Ymin, Ymax = self.Yminmax
        return dedent(f'''
        G0 X{Xmin:.7} Y{Ymin:.7}
        G1 F9600 S5
        G1 X{Xmax:.7} Y{Ymin:.7}
        G1 X{Xmax:.7} Y{Ymax:.7}
        G1 X{Xmin:.7} Y{Ymax:.7}
        G1 X{Xmin:.7} Y{Ymin:.7}
        G0 X0 Y0
        ''').strip().encode('utf-8') + b'\n'    

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
        self.regex = re.compile(r'(X|Y|Z)[-0-9\.]+')

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
