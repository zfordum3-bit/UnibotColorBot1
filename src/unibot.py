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
import time
import numpy as np

from aim_output import AimOutput
from cheats import Cheats
from mouse import get_mouse_implementation
from screen import Screen
from utils import Utils

# #region debug log
_LOG_PATH = r"debug.log"
def _log(msg, data=None):
    return
# #endregion


class Unibot:
    def run(self):
        self.print_license()
        while True:
            # Track delta time
            start_time = time.time()

            utils = Utils()
            config = utils.config
            cheats = Cheats(config)
            mouse = get_mouse_implementation(config)
            aim_output = AimOutput(config, mouse)
            screen = Screen(config)
            aim_output.start()
            previous_aim_active = False

            print('Unibot ON')

            # Cheat loop
            while True:
                delta_time = time.time() - start_time
                start_time = time.time()
                
                reload_config = utils.check_key_binds()
                if reload_config:
                    break

                aim_active = utils.get_aim_state()
                trigger_active = utils.get_trigger_state()
                if previous_aim_active and not aim_active:
                    screen.release_aim_lock()
                    cheats.calculate_aim(False, None)
                    aim_output.set_move(0, 0)
                previous_aim_active = aim_active

                if (aim_active or trigger_active) or (config.debug and config.debug_always_on):
                    # Get target position and check if there is a target in the center of the screen
                    target, trigger = screen.get_target(cheats.recoil_offset, aim_active)

                    # #region debug log
                    _log("unibot_loop", {
                        "aim_active": aim_active,
                        "target": target,
                        "trigger": trigger,
                        "aim_state": cheats.aim_state,
                        "move_pre": (cheats.move_x, cheats.move_y)
                    })
                    # #endregion

                    # Shoot if target in the center of the screen
                    if trigger_active and trigger:
                        if config.trigger_delay != 0:
                            delay_before_click = (np.random.randint(config.trigger_randomization) + config.trigger_delay) / 1000
                        else:
                            delay_before_click = 0
                        mouse.click(delay_before_click)

                    # Calculate movement based on target position
                    cheats.calculate_aim(aim_active, target)

                    # #region debug log
                    _log("unibot_after_aim", {
                        "aim_active": aim_active,
                        "target": target,
                        "aim_state": cheats.aim_state,
                        "move_post": (cheats.move_x, cheats.move_y)
                    })
                    # #endregion

                if utils.get_rapid_fire_state():
                    mouse.click()

                # Apply recoil
                cheats.apply_recoil(utils.recoil_state, delta_time)

                # Send the latest correction to the 240Hz output worker. Zero
                # corrections intentionally clear any unfinished old movement.
                aim_output.set_move(cheats.move_x, cheats.move_y)

                # Reset move values so the aim doesn't keep drifting when no targets are on the screen
                cheats.move_x, cheats.move_y = (0, 0)

                # Do not loop above the set refresh rate
                time_spent = (time.time() - start_time) * 1000
                if time_spent < config.min_loop_time:
                    time.sleep((config.min_loop_time - time_spent) / 1000)

            aim_output.stop()
            screen.close()
            del utils
            del cheats
            del mouse
            del screen
            del aim_output
            print('Reloading')
        
    def print_license(self):
        print('Unibot  Copyright (C) 2025  vike256 \n'
              'This program comes with ABSOLUTELY NO WARRANTY. \n'
              'This is free software, and you are welcome to redistribute it under certain conditions. \n'
              'For details see <LICENSE.txt>.')
