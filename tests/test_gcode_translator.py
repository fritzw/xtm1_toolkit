#!/usr/bin/env python3

import re
import pytest
import os
import sys
current_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(current_dir, '..'))

from xtm1 import GcodeTranslator

@pytest.fixture
def translator():
    return GcodeTranslator()

@pytest.fixture
def bare_translator():
    translator = GcodeTranslator()
    translator.START_GCODE = b''
    translator.END_GCODE = b''
    return translator

def test_empty_lines(translator: GcodeTranslator):
    assert translator.process_line(b'') == b''
    assert translator.process_line(b' ') == b''
    assert translator.process_line(b'  \t \n') == b''
    assert len(translator.filtered_lines) == 0

TEST_GCODE_1 = b'''
G1 X1 Y1
G1 X2 Y2 F1000 S1000
G0 X3 Y3
'''

def test_header_footer(translator: GcodeTranslator):
    output = translator.translate_file_content(TEST_GCODE_1)
    header_pos = output.index(translator.START_GCODE)
    gcode_pos = output.index(TEST_GCODE_1)
    footer_pos = output.index(translator.END_GCODE)
    assert header_pos < gcode_pos < footer_pos
    assert len(translator.filtered_lines) == 0

TEST_GCODE_2 = b'''
M4 S100
M04
M05
M5 ; comment
M3 S10
G1 X1 Y1
'''

def test_gcode_removal(translator: GcodeTranslator):
    output = translator.translate_file_content(TEST_GCODE_2)
    print(output)
    assert translator.filtered_lines == { b'M04', b'M4 S100', b'M05', b'M5 ; comment', b'M3 S10' }
    without_header = output.replace(translator.START_GCODE, b'')
    without_footer = without_header.replace(translator.END_GCODE, b'')
    rest = re.sub(b'^;.*?$', b'', without_footer, flags=re.MULTILINE)
    assert rest.strip() == b'G1 X1 Y1'

def test_reject_unknown_gcodes(translator: GcodeTranslator):
    with pytest.raises(ValueError):
        translator.translate_file_content(b'G1 X1 Y1\nM123\nG0 X2 Y2')

TEST_GCODE_Z1 = b'''
G1 Z0 X1 Y1
G1 Z1 X2 Y2
G1 Z-1 X3 Y3
'''

def test_invert_z_axis(bare_translator: GcodeTranslator):
    output = bare_translator.translate_file_content(TEST_GCODE_Z1)
    assert output == b'''
G1 Z17.0 X1 Y1
G1 Z16.0 X2 Y2
G1 Z18.0 X3 Y3
'''
    bare_translator.material_height_zero_z = 20.5
    output = bare_translator.translate_file_content(TEST_GCODE_Z1)
    assert output == b'''
G1 Z20.5 X1 Y1
G1 Z19.5 X2 Y2
G1 Z21.5 X3 Y3
'''
    
def test_z_safety_check(bare_translator: GcodeTranslator):
    with pytest.raises(RuntimeError):
        bare_translator.lowest_z_height = 15
        bare_translator.translate_file_content(TEST_GCODE_Z1)

def test_translate_file(bare_translator: GcodeTranslator):
    in_file = os.path.join(current_dir, 'test-gcode/lasse.gcode')
    zero_z = 15.0
    bare_translator.material_height_zero_z = zero_z
    new_file = bare_translator.translate_file(in_file)
    assert new_file == in_file.replace('lasse.gcode', 'lasse.xtm1.gcode')
    with open(new_file, 'rb') as f:
        lines = set(f.readlines())
        assert b';--M05\n' in lines
        assert f'G0 Z{zero_z}\n'.encode('utf-8') in lines
    os.unlink(new_file)

if __name__ == '__main__':
    sys.exit(pytest.main())