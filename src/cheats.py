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
import win32api


class Cheats:
    ACQUIRE = 'acquire'
    TRACK = 'track'
    LOCK = 'lock'
    LOCK_EPSILON = 0.55
    LOCK_RELEASE_EPSILON = 1.25

    def __init__(self, config):
        self.cfg = config
        self.move_x, self.move_y = (0, 0)
        self.previous_x, self.previous_y = (0, 0)
        self.previous_target_x, self.previous_target_y = (0, 0)
        self.aim_state = self.ACQUIRE
        self.recoil_offset = 0
        self.recoil_move_x, self.recoil_move_y = (0, 0)

    def calculate_aim(self, state, target):
        if state and target is not None:
            target_x, target_y = target
            distance = (target_x**2 + target_y**2) ** 0.5

            if distance <= self.LOCK_EPSILON:
                self.previous_x, self.previous_y = (0, 0)
                self.previous_target_x, self.previous_target_y = (target_x, target_y)
                self.aim_state = self.LOCK
                self.move_x, self.move_y = (0, 0)
                return

            self.aim_state = self.LOCK if distance <= self.LOCK_RELEASE_EPSILON else self.TRACK
            smoothing = min(max(self.cfg.aim_smoothing_factor, 0.0), 1.0)
            desired_x = target_x * self.cfg.speed * getattr(self.cfg, 'x_speed_multiplier', 1.0)
            desired_y = target_y * self.cfg.speed * self.cfg.y_speed_multiplier

            x = (1 - smoothing) * self.previous_x + smoothing * desired_x
            y = (1 - smoothing) * self.previous_y + smoothing * desired_y

            x = self.limit_to_error(x, target_x)
            y = self.limit_to_error(y, target_y)

            x, y = self.clamp_step(x, y)

            self.previous_x, self.previous_y = (x, y)
            self.previous_target_x, self.previous_target_y = (target_x, target_y)
            self.move_x, self.move_y = (x, y)
        else:
            self.previous_x, self.previous_y = (0, 0)
            self.previous_target_x, self.previous_target_y = (0, 0)
            self.aim_state = self.ACQUIRE

    def clamp_step(self, x, y):
        max_step = self.cfg.aim_max_step
        distance = max((x**2 + y**2) ** 0.5, 1)
        if distance <= max_step:
            return x, y

        scale = max_step / distance
        return x * scale, y * scale

    @staticmethod
    def limit_to_error(move, error):
        if move == 0 or error == 0:
            return 0

        if (move > 0) != (error > 0):
            return 0
        error_abs = abs(error)
        max_fraction = 0.62 if error_abs <= 6 else 0.86
        max_move = error_abs * max_fraction
        if abs(move) > max_move:
            return max_move if move > 0 else -max_move
        return move

    def apply_recoil(self, state, delta_time):
        if state and delta_time != 0:
            if self.cfg.recoil_mode == 'move' and win32api.GetAsyncKeyState(0x01) < 0:
                raw_x = self.cfg.recoil_x * delta_time
                raw_y = self.cfg.recoil_y * delta_time
                if self.aim_state == self.LOCK:
                    raw_x *= 0.30
                    raw_y *= 0.30
                elif self.aim_state == self.TRACK:
                    raw_x *= 0.55
                    raw_y *= 0.55

                recoil_distance = max(abs(raw_x), abs(raw_y))
                max_recoil_step = self.cfg.aim_max_step * 0.6
                if recoil_distance > max_recoil_step:
                    scale = max_recoil_step / recoil_distance
                    raw_x *= scale
                    raw_y *= scale
                self.recoil_move_x = self.recoil_move_x * 0.58 + raw_x * 0.42
                self.recoil_move_y = self.recoil_move_y * 0.58 + raw_y * 0.42
                self.move_x += self.recoil_move_x
                self.move_y += self.recoil_move_y
            elif self.cfg.recoil_mode == 'offset':
                if win32api.GetAsyncKeyState(0x01) < 0:
                    if self.recoil_offset < self.cfg.max_offset:
                        self.recoil_offset += self.cfg.recoil_y * delta_time
                        if self.recoil_offset > self.cfg.max_offset:
                            self.recoil_offset = self.cfg.max_offset
                else:
                    if self.recoil_offset > 0:
                        self.recoil_offset -= self.cfg.recoil_recover * delta_time
                        if self.recoil_offset < 0:
                            self.recoil_offset = 0
        else:
            self.recoil_offset = 0
            self.recoil_move_x *= 0.45
            self.recoil_move_y *= 0.45
