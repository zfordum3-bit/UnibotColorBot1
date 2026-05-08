"""
    Unibot, an open-source colorbot.
    Copyright (C) 2025 vike256

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
from configparser import ConfigParser
import numpy as np
import os


class ConfigReader:
    def __init__(self):
        self.parser = ConfigParser()

        # Communication
        self.bot_input_type = None
        self.microcontroller_ip = None
        self.microcontroller_port = None
        self.com_port = None

        # Screen
        self.group_close_target_blobs_threshold = None
        self.upper_color = None
        self.lower_color = None
        self.capture_fov_x = None
        self.capture_fov_y = None
        self.aim_fov_x = None
        self.aim_fov_y = None
        self.min_loop_time = None
        self.auto_detect_resolution = None
        self.resolution_x = None
        self.resolution_y = None

        # Aim
        self.screen_center_offset = None
        self.aim_smoothing_factor = None
        self.aim_deadzone = None
        self.aim_max_step = None
        self.aim_output_hz = None
        self.aim_output_blend_ticks = None
        self.target_prediction = None
        self.speed = None
        self.x_speed_multiplier = None
        self.y_speed_multiplier = None
        self.aim_height = None
        self.aim_target_part = None
        self.aim_height_near = None
        self.aim_height_mid = None
        self.aim_height_far = None
        self.color_confidence = None
        self.head_offset_near = None
        self.head_offset_mid = None
        self.head_offset_far = None
        self.head_roi_ratio = None
        self.target_lock_frames = None
        self.target_switch_margin = None

        # Recoil
        self.recoil_mode = None
        self.recoil_x = None
        self.recoil_y = None
        self.max_offset = None
        self.recoil_recover = None

        # Trigger
        self.trigger_delay = None
        self.trigger_randomization = None
        self.trigger_threshold = None

        # Rapid fire
        self.target_cps = None

        # Key binds
        self.key_reload_config = None
        self.key_toggle_aim = None
        self.key_toggle_recoil = None
        self.key_exit = None
        self.key_trigger = None
        self.key_rapid_fire = None
        self.aim_keys = []

        # Debug
        self.debug = None
        self.debug_always_on = None
        self.display_mode = None
        self.debug_refresh_interval = None

        # Get config path and read it
        self.path = os.path.join(os.path.dirname(__file__), '../config.ini')
        self.parser.read(self.path)

    def read_config(self):
        self.aim_keys = []

        # Get aim settings
        value = self.parser.get('aim', 'bot_input_type').lower()
        bot_input_type_list = ['winapi', 'interception_driver', 'microcontroller_serial', 'microcontroller_socket']
        if value in bot_input_type_list:
            self.bot_input_type = value
        else:
            print('WARNING: Invalid bot_input_type value')
        
        self.screen_center_offset = int(self.parser.get('aim', 'screen_center_offset'))

        value = float(self.parser.get('aim', 'aim_smoothing_factor'))
        if 0 <= value <= 1:
            self.aim_smoothing_factor = value
        else:
            print('WARNING: Invalid aim_smoothing_factor value')

        self.aim_deadzone = int(self.parser.get('aim', 'aim_deadzone', fallback='4'))
        self.aim_max_step = float(self.parser.get('aim', 'aim_max_step', fallback='55'))
        self.aim_output_hz = int(self.parser.get('aim', 'aim_output_hz', fallback='240'))
        self.aim_output_blend_ticks = int(self.parser.get('aim', 'aim_output_blend_ticks', fallback='3'))
        self.target_prediction = float(self.parser.get('aim', 'target_prediction', fallback='0.20'))
        self.speed = float(self.parser.get('aim', 'speed'))
        self.x_speed_multiplier = float(self.parser.get('aim', 'x_speed_multiplier', fallback='1'))
        self.y_speed_multiplier = float(self.parser.get('aim', 'y_speed_multiplier'))

        self.aim_target_part = self.parser.get('aim', 'aim_target_part', fallback='head').strip().lower()
        if self.aim_target_part not in ('head', 'neck', 'body', 'visible'):
            print('WARNING: Invalid aim_target_part value')
            self.aim_target_part = 'head'

        self.aim_height_near = self.read_unit_float('aim', 'aim_height_near', 'head_offset_near', 0.50)
        self.aim_height_mid = self.read_unit_float('aim', 'aim_height_mid', 'head_offset_mid', 0.55)
        self.aim_height_far = self.read_unit_float('aim', 'aim_height_far', 'head_offset_far', 0.65)
        self.color_confidence = self.read_unit_float('aim', 'color_confidence', None, 0.40)

        self.aim_height = self.aim_height_mid
        self.head_offset_near = self.aim_height_near
        self.head_offset_mid = self.aim_height_mid
        self.head_offset_far = self.aim_height_far

        self.head_roi_ratio = float(self.parser.get('aim', 'head_roi_ratio', fallback='0.30'))
        self.target_lock_frames = int(self.parser.get('aim', 'target_lock_frames', fallback='5'))
        self.target_switch_margin = float(self.parser.get('aim', 'target_switch_margin', fallback='0.50'))

        # Get communication settings
        match self.bot_input_type:
            case 'microcontroller_socket':
                self.microcontroller_ip = self.parser.get('communication', 'microcontroller_ip')
                self.microcontroller_port = int(self.parser.get('communication', 'microcontroller_port'))
            case 'microcontroller_serial':
                self.com_port = self.parser.get('communication', 'com_port')

        # Get screen settings
        values_str = self.parser.get('screen', 'group_close_target_blobs_threshold').split(',')
        self.group_close_target_blobs_threshold = (int(values_str[0].strip()), int(values_str[1].strip()))

        upper_color = self.parser.get('screen', 'upper_color').split(',')
        lower_color = self.parser.get('screen', 'lower_color').split(',')
        for i in range(0, 3):
            upper_color[i] = int(upper_color[i].strip())
        for i in range(0, 3):
            lower_color[i] = int(lower_color[i].strip())
        self.upper_color = np.array(upper_color)
        self.lower_color = np.array(lower_color)

        self.capture_fov_x = int(self.parser.get('screen', 'capture_fov_x'))
        self.capture_fov_y = int(self.parser.get('screen', 'capture_fov_y'))
        self.aim_fov_x = int(self.parser.get('screen', 'aim_fov_x'))
        self.aim_fov_y = int(self.parser.get('screen', 'aim_fov_y'))
        max_loops_per_sec = int(self.parser.get('screen', 'max_loops_per_sec'))
        self.min_loop_time = 1000 / max_loops_per_sec

        value = self.parser.get('screen', 'auto_detect_resolution').lower()
        if value == 'true':
            self.auto_detect_resolution = True
        else:
            self.auto_detect_resolution = False

        self.resolution_x = int(self.parser.get('screen', 'resolution_x'))
        self.resolution_y = int(self.parser.get('screen', 'resolution_y'))

        # Get recoil settings
        value = self.parser.get('recoil', 'mode').lower()
        recoil_mode_list = ['move', 'offset']
        if value in recoil_mode_list:
            self.recoil_mode = value
        else:
            print('WARNING: Invalid recoil_mode value')

        self.recoil_x = float(self.parser.get('recoil', 'recoil_x'))
        self.recoil_y = float(self.parser.get('recoil', 'recoil_y'))
        self.max_offset = int(self.parser.get('recoil', 'max_offset'))
        self.recoil_recover = float(self.parser.get('recoil', 'recover'))

        # Get trigger settings
        self.trigger_delay = int(self.parser.get('trigger', 'trigger_delay'))
        self.trigger_randomization = int(self.parser.get('trigger', 'trigger_randomization'))
        self.trigger_threshold = int(self.parser.get('trigger', 'trigger_threshold'))

        # Get rapid fire settings
        self.target_cps = int(self.parser.get('rapid_fire', 'target_cps'))

        # Get keybind settings
        self.key_reload_config = self.read_hex(self.parser.get('key_binds', 'key_reload_config'))
        self.key_toggle_aim = self.read_hex(self.parser.get('key_binds', 'key_toggle_aim'))
        self.key_toggle_recoil = self.read_hex(self.parser.get('key_binds', 'key_toggle_recoil'))
        self.key_exit = self.read_hex(self.parser.get('key_binds', 'key_exit'))
        self.key_trigger = self.read_hex(self.parser.get('key_binds', 'key_trigger'))
        self.key_rapid_fire = self.read_hex(self.parser.get('key_binds', 'key_rapid_fire'))
        aim_keys_str = self.parser.get('key_binds', 'aim_keys')
        if not aim_keys_str == 'off':
            aim_keys_str = aim_keys_str.split(',')
            for key in aim_keys_str:
                self.aim_keys.append(self.read_hex(key))
        else:
            self.aim_keys = ['off']

        # Get debug settings
        value = self.parser.get('debug', 'enabled').lower()
        if value == 'true':
            self.debug = True
        else:
            self.debug = False

        value = self.parser.get('debug', 'always_on').lower()
        if value == 'true':
            self.debug_always_on = True
        else:
            self.debug_always_on = False

        value = self.parser.get('debug', 'display_mode').lower()
        display_mode_list = ['game', 'mask']
        if value in display_mode_list:
            self.display_mode = value
        else:
            print('WARNING: Invalid display_mode value')

        self.debug_refresh_interval = int(self.parser.get('debug', 'refresh_interval', fallback='4'))

    @staticmethod
    def read_hex(string):
        if string.lower() == 'off':
            return 'off'
        return int(string, 16)

    def read_unit_float(self, section, option, legacy_option=None, fallback=0.0):
        value = self.parser.get(section, option, fallback=None)
        if value is None and legacy_option is not None:
            value = self.parser.get(section, legacy_option, fallback=None)
        if value is None:
            return float(fallback)

        try:
            parsed = float(value)
        except ValueError:
            print(f'WARNING: Invalid {option} value')
            return float(fallback)

        if 0 <= parsed <= 1:
            return parsed

        print(f'WARNING: Invalid {option} value')
        return float(fallback)
