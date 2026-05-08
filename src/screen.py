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
import cv2
import numpy as np
import bettercam
import threading
import os
import time
from configparser import ConfigParser
from pyautogui import size

try:
    import tkinter as tk
    import win32con
    import win32gui
except Exception:
    tk = None
    win32con = None
    win32gui = None

def _log(msg, data=None):
    return


class FovOverlay:
    TRANSPARENT_COLOR = '#ff00ff'
    TRANSPARENT_COLORREF = 0x00FF00FF
    CIRCLE_COLOR = '#ffff00'

    def __init__(self, screen, aim_fov, config_path=None):
        self.screen = screen
        self.aim_fov = aim_fov
        self.config_path = config_path
        self.config_mtime = self.get_config_mtime()
        self.canvas = None
        self.circle_id = None
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        if tk is None or win32gui is None or win32con is None:
            return

        root = None
        try:
            root = tk.Tk()
            root.overrideredirect(True)
            root.configure(bg=self.TRANSPARENT_COLOR)
            root.attributes('-topmost', True)
            root.attributes('-transparentcolor', self.TRANSPARENT_COLOR)
            root.geometry(f'{self.screen[0]}x{self.screen[1]}+0+0')

            canvas = tk.Canvas(
                root,
                width=self.screen[0],
                height=self.screen[1],
                bg=self.TRANSPARENT_COLOR,
                highlightthickness=0,
                bd=0
            )
            canvas.pack(fill='both', expand=True)
            self.canvas = canvas

            self.draw_circle()

            root.update_idletasks()
            root.update()
            self.make_click_through(root.winfo_id())
            self.keep_alive(root)
            root.mainloop()
        except Exception:
            if root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass

    def keep_alive(self, root):
        if self.stop_event.is_set():
            root.destroy()
            return

        try:
            root.lift()
            root.attributes('-topmost', True)
        except Exception:
            pass
        self.refresh_from_config()
        root.after(250, lambda: self.keep_alive(root))

    def draw_circle(self):
        if self.canvas is None:
            return

        center_x = self.screen[0] // 2
        center_y = self.screen[1] // 2
        radius = int(min(self.aim_fov[0], self.aim_fov[1]))

        if self.circle_id is None:
            self.circle_id = self.canvas.create_oval(
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
                outline=self.CIRCLE_COLOR,
                width=2
            )
        else:
            self.canvas.coords(
                self.circle_id,
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius
            )

    def refresh_from_config(self):
        if not self.config_path:
            return

        mtime = self.get_config_mtime()
        if mtime is None or mtime == self.config_mtime:
            return
        self.config_mtime = mtime

        aim_fov = self.read_aim_fov()
        if aim_fov is None or aim_fov == self.aim_fov:
            return

        self.aim_fov = aim_fov
        self.draw_circle()

    def read_aim_fov(self):
        parser = ConfigParser()
        try:
            parser.read(self.config_path)
            return (
                int(parser.get('screen', 'aim_fov_x')),
                int(parser.get('screen', 'aim_fov_y'))
            )
        except Exception:
            return None

    def get_config_mtime(self):
        try:
            return os.path.getmtime(self.config_path)
        except (OSError, TypeError):
            return None

    @staticmethod
    def make_click_through(hwnd):
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        style |= (
            win32con.WS_EX_LAYERED |
            win32con.WS_EX_TRANSPARENT |
            win32con.WS_EX_TOPMOST |
            win32con.WS_EX_TOOLWINDOW
        )
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style)
        win32gui.SetLayeredWindowAttributes(
            hwnd,
            FovOverlay.TRANSPARENT_COLORREF,
            0,
            win32con.LWA_COLORKEY
        )

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=0.5)


class Screen:
    def __init__(self, config):
        self.cfg = config
        self.cam = bettercam.create(output_color="BGR")

        if self.cfg.auto_detect_resolution:
            screen_size = size()
            self.screen = (screen_size.width, screen_size.height)
        else:
            self.screen = (self.cfg.resolution_x, self.cfg.resolution_y)

        self.screen_center = (self.screen[0] // 2, self.screen[1] // 2)
        self.screen_region = (
            0,
            0,
            self.screen[0],
            self.screen[1]
        )
        self.fov = (self.cfg.capture_fov_x, self.cfg.capture_fov_y)
        self.fov_center = (self.fov[0] // 2, self.fov[1] // 2)
        self.fov_region = (
            self.screen_center[0] - self.fov[0] // 2,
            self.screen_center[1] - self.fov[1] // 2 - self.cfg.screen_center_offset,
            self.screen_center[0] + self.fov[0] // 2,
            self.screen_center[1] + self.fov[1] // 2 - self.cfg.screen_center_offset
        )
        self.thresh = None
        self.target = None
        self.closest_contour = None
        self.locked_target = None
        self.locked_body = None
        self.locked_body_center = None
        self.locked_body_velocity = np.array((0.0, 0.0), dtype=float)
        self.locked_head_window = None
        self.stable_head_center = None
        self.lock_misses = 0
        self.aim_was_active = False
        self.filtered_target = None
        self.previous_target = None
        self.last_measurement = None
        self.measurement_velocity = np.array((0.0, 0.0), dtype=float)
        self.track_position = None
        self.track_velocity = (0, 0)
        self.track_acceleration = (0, 0)
        self.debug_candidates = []
        self.debug_frame = 0
        self.img = None
        self.last_img = None
        self.aim_fov = (self.cfg.aim_fov_x, self.cfg.aim_fov_y)
        self.config_path = getattr(self.cfg, 'path', None)
        self.fov_config_mtime = self.get_config_mtime()
        self._fall_history = []
        self.fov_overlay = None

        # Setup debug display
        if self.cfg.debug:
            self.display_mode = self.cfg.display_mode
            self.window_name = 'Python'
            debug_width = max(360, self.screen[0] // 4)
            self.window_resolution = (
                debug_width,
                max(200, int(debug_width * self.screen[1] / self.screen[0]))
            )
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            self.position_debug_window()
            self.fov_overlay = FovOverlay(self.screen, self.aim_fov, self.config_path)

    def __del__(self):
        self.close()
        if hasattr(self, 'cam'):
            del self.cam

    def close(self):
        if getattr(self, 'fov_overlay', None) is not None:
            self.fov_overlay.close()
            self.fov_overlay = None
        if getattr(self.cfg, 'debug', False) and hasattr(self, 'window_name'):
            try:
                cv2.destroyWindow(self.window_name)
            except cv2.error:
                pass

    def refresh_aim_fov_from_config(self):
        if not getattr(self, 'config_path', None):
            return

        mtime = self.get_config_mtime()
        if mtime is None or mtime == self.fov_config_mtime:
            return
        self.fov_config_mtime = mtime

        parser = ConfigParser()
        try:
            parser.read(self.config_path)
            aim_fov = (
                int(parser.get('screen', 'aim_fov_x')),
                int(parser.get('screen', 'aim_fov_y'))
            )
        except Exception:
            return

        if aim_fov == self.aim_fov:
            return

        self.aim_fov = aim_fov
        self.cfg.aim_fov_x, self.cfg.aim_fov_y = aim_fov

    def get_config_mtime(self):
        try:
            return os.path.getmtime(getattr(self, 'config_path', None))
        except (OSError, TypeError):
            return None

    def screenshot(self, region):
        width = max(1, int(region[2] - region[0]))
        height = max(1, int(region[3] - region[1]))

        for _ in range(6):
            image = self.cam.grab(region)
            if image is not None:
                frame = np.array(image)
                self.last_img = frame
                return frame
            time.sleep(0.001)

        if self.last_img is not None and self.last_img.shape[:2] == (height, width):
            return self.last_img.copy()

        return np.zeros((height, width, 3), dtype=np.uint8)

    def get_target(self, recoil_offset, aim_active=False):
        self.refresh_aim_fov_from_config()

        # Convert the offset to an integer, since it is used to define the capture region
        recoil_offset = int(recoil_offset)

        # Reset variables
        self.target = None
        trigger = False
        self.closest_contour = None
        self.debug_candidates = []

        if not aim_active and self.aim_was_active:
            self.clear_lock()
        pressed_this_frame = aim_active and not self.aim_was_active
        self.aim_was_active = aim_active

        # Capture a screenshot
        self.img = self.screenshot(self.get_region(self.fov_region, recoil_offset))

        # Convert the screenshot to HSV color space for color detection
        hsv = cv2.cvtColor(self.img, cv2.COLOR_BGR2HSV)

        # Create a mask to identify pixels within the specified color range.
        # Purple outlines are strongest at high saturation/value; closing preserves
        # distant outline structure without inflating every blob into the chest.
        mask = cv2.inRange(hsv, self.cfg.lower_color, self.cfg.upper_color)
        clean_kernel = np.ones((3, 3), np.uint8)
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, clean_kernel, iterations=1)
        kernel = np.ones((self.cfg.group_close_target_blobs_threshold[0], self.cfg.group_close_target_blobs_threshold[1]), np.uint8)
        dilated = cv2.dilate(closed, kernel, iterations=2)

        # Apply thresholding to convert the mask into a binary image
        self.thresh = cv2.threshold(dilated, 60, 255, cv2.THRESH_BINARY)[1]

        # Find contours of the detected color blobs
        # #region debug log
        _log("findContours pre-call", {"closed_shape": closed.shape, "thresh_shape": self.thresh.shape})
        # #endregion
        try:
            result_raw = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            _log("findContours raw result", {"len": len(result_raw), "type": str(type(result_raw))})
            if len(result_raw) == 3:
                _, raw_contours, _ = result_raw
            else:
                raw_contours, _ = result_raw
        except Exception as e:
            _log("findContours raw ERROR", {"error": str(e)})
            raw_contours = []
        try:
            result_cnt = cv2.findContours(self.thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            _log("findContours thresh result", {"len": len(result_cnt)})
            if len(result_cnt) == 3:
                _, contours, _ = result_cnt
            else:
                contours, _ = result_cnt
        except Exception as e:
            _log("findContours thresh ERROR", {"error": str(e)})
            contours = []
        # #endregion

        if len(contours) != 0:
            target_groups = []
            for contour in contours:
                # Make a bounding rectangle for the target
                rect_x, rect_y, rect_w, rect_h = cv2.boundingRect(contour)
                if rect_w * rect_h < 4:
                    continue
                rect = (rect_x, rect_y, rect_x + rect_w, rect_y + rect_h)

                merged = False
                for index, group in enumerate(target_groups):
                    if self.rect_distance(rect, group) <= self.group_distance(rect, group):
                        target_groups[index] = (
                            min(group[0], rect[0]),
                            min(group[1], rect[1]),
                            max(group[2], rect[2]),
                            max(group[3], rect[3])
                        )
                        merged = True
                        break

                if not merged:
                    target_groups.append(rect)

            # A merge can make separate groups touch another group, so repeat until stable.
            changed = True
            while changed:
                changed = False
                merged_groups = []
                for group in target_groups:
                    for index, merged_group in enumerate(merged_groups):
                        if self.rect_distance(group, merged_group) <= self.group_distance(group, merged_group):
                            merged_groups[index] = (
                                min(group[0], merged_group[0]),
                                min(group[1], merged_group[1]),
                                max(group[2], merged_group[2]),
                                max(group[3], merged_group[3])
                            )
                            changed = True
                            break
                    else:
                        merged_groups.append(group)
                target_groups = merged_groups

            candidates = self.make_simple_lock_candidates(target_groups, raw_contours, closed)
            if candidates:
                self.debug_candidates = candidates
                target_candidate = self.choose_simple_candidate(candidates, aim_active, pressed_this_frame)
                if target_candidate is not None:
                    self.apply_simple_candidate(target_candidate, aim_active)
                else:
                    self.hold_or_miss_simple_lock()
            else:
                self.hold_or_miss_simple_lock()

            if self.target is not None and (
                    abs(self.target[0]) <= self.cfg.trigger_threshold and
                    abs(self.target[1]) <= self.cfg.trigger_threshold
            ):
                trigger = True
            elif self.closest_contour is not None and (
                # Check if crosshair is inside the closest target
                cv2.pointPolygonTest(
                    self.closest_contour, (self.fov_center[0], self.fov_center[1]), False) >= 0 and

                # Eliminate a lot of false positives by also checking pixels near the crosshair.
                cv2.pointPolygonTest(
                    self.closest_contour, (self.fov_center[0] + self.cfg.trigger_threshold, self.fov_center[1]), False) >= 0 and
                cv2.pointPolygonTest(
                    self.closest_contour, (self.fov_center[0] - self.cfg.trigger_threshold, self.fov_center[1]), False) >= 0 and
                cv2.pointPolygonTest(
                    self.closest_contour, (self.fov_center[0], self.fov_center[1] + self.cfg.trigger_threshold), False) >= 0 and
                cv2.pointPolygonTest(
                    self.closest_contour, (self.fov_center[0], self.fov_center[1] - self.cfg.trigger_threshold), False) >= 0
            ):
                trigger = True

        if self.cfg.debug and self.should_refresh_debug():
            self.run_debug_window(recoil_offset)

        return self.target, trigger

    def make_simple_lock_candidates(self, target_groups, raw_contours, mask):
        candidates = []
        for group in target_groups:
            group_candidates = self.split_simple_group(group, raw_contours, mask)
            if not group_candidates:
                group_candidates = [group]

            for rect in group_candidates:
                candidate = self.make_simple_candidate(rect, mask)
                if candidate is not None:
                    candidates.append(candidate)

        candidates.sort(key=self.simple_candidate_score)
        return candidates

    def split_simple_group(self, rect, raw_contours, mask):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        if rect_w < 42 or rect_w / max(rect_h, 1) < 1.35:
            return []

        head_limit = rect_y1 + max(8, int(rect_h * 0.42))
        component_rects = []
        for contour in raw_contours:
            x, y, w, h = cv2.boundingRect(contour)
            contour_rect = (x, y, x + w, y + h)
            if not self.rect_overlap(contour_rect, rect):
                continue
            if y > head_limit:
                continue
            if w * h < 8:
                continue

            expanded_w = max(w * 1.15, min(rect_h * 0.90, 34), 14)
            center_x = x + w / 2
            sub_rect = (
                max(rect_x1, int(center_x - expanded_w / 2)),
                rect_y1,
                min(rect_x2, int(center_x + expanded_w / 2)),
                rect_y2
            )
            if sub_rect[2] > sub_rect[0] and sub_rect[3] > sub_rect[1]:
                component_rects.append(sub_rect)

        component_rects = self.merge_split_components(component_rects)
        return component_rects if len(component_rects) >= 2 else []

    def make_simple_candidate(self, rect, mask):
        visible_rect, pixels = self.visible_mask_rect(rect, mask)
        if visible_rect is None:
            return None

        rect_x1, rect_y1, rect_x2, rect_y2 = visible_rect
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        if rect_w <= 0 or rect_h <= 0:
            return None

        area = rect_w * rect_h
        colored = int(np.count_nonzero(pixels))
        fill_ratio = colored / max(area, 1)
        aspect = rect_w / max(rect_h, 1)

        if not self.accept_simple_visible_rect(visible_rect, colored, fill_ratio, aspect):
            return None

        target_point, source, head_window = self.simple_target_point(visible_rect, mask)
        if target_point is None:
            return None

        target = (target_point[0] - self.fov_center[0], target_point[1] - self.fov_center[1])
        if not self.within_aim_fov(target):
            return None

        body_center = self.rect_center(visible_rect)
        distance = float(np.hypot(target[0], target[1]))
        model_confidence = self.body_model_confidence(visible_rect, mask)
        confidence = self.simple_confidence(source, model_confidence, visible_rect, fill_ratio)
        if confidence < self.min_color_confidence(source):
            return None

        return {
            'rect': head_window if head_window is not None else visible_rect,
            'body_rect': visible_rect,
            'target': target,
            'center': target_point,
            'body_center': body_center,
            'head_window': head_window if head_window is not None else visible_rect,
            'source': source,
            'confidence': confidence,
            'model_confidence': model_confidence,
            'score': distance
        }

    def visible_mask_rect(self, rect, mask):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        x1 = max(0, int(rect_x1))
        y1 = max(0, int(rect_y1))
        x2 = min(mask.shape[1], int(rect_x2))
        y2 = min(mask.shape[0], int(rect_y2))
        if x2 <= x1 or y2 <= y1:
            return None, None

        roi = mask[y1:y2, x1:x2] > 0
        ys, xs = np.where(roi)
        if len(xs) == 0:
            return None, None

        visible_rect = (
            int(x1 + xs.min()),
            int(y1 + ys.min()),
            int(x1 + xs.max() + 1),
            int(y1 + ys.max() + 1)
        )
        visible_pixels = mask[visible_rect[1]:visible_rect[3], visible_rect[0]:visible_rect[2]] > 0
        return visible_rect, visible_pixels

    def accept_simple_visible_rect(self, rect, colored, fill_ratio, aspect):
        rect_w = rect[2] - rect[0]
        rect_h = rect[3] - rect[1]
        rect_area = rect_w * rect_h
        fov_area = max(self.fov[0] * self.fov[1], 1)
        near_body_like = self.is_near_body_like_rect(rect_w, rect_h, fill_ratio, aspect)
        if colored < 12:
            return False
        max_area_ratio = 0.50 if near_body_like else 0.22
        if rect_area > fov_area * max_area_ratio:
            return False
        if aspect > 3.0 and rect_h < 36:
            return False
        if aspect < 0.10:
            return False
        if fill_ratio > 0.58 and rect_w >= 8 and rect_h >= 8 and not near_body_like:
            return False
        if near_body_like and fill_ratio > 0.78:
            return False
        if rect_w <= 14 and rect_h <= 14 and fill_ratio > 0.38:
            return False
        return True

    def is_near_body_like_rect(self, rect_w, rect_h, fill_ratio, aspect):
        height_ratio = rect_h / max(self.fov[1], 1)
        width_ratio = rect_w / max(self.fov[0], 1)
        return (
            height_ratio >= 0.38 and
            width_ratio <= 0.82 and
            0.16 <= aspect <= 1.70 and
            0.03 <= fill_ratio <= 0.78
        )

    def simple_target_point(self, rect, mask):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        if getattr(self.cfg, 'aim_target_part', 'head') == 'visible':
            return self.visible_color_center(rect, mask), 'simple_visible', rect

        head_ratio = self.get_head_roi_ratio(rect)
        head_window = (
            rect_x1,
            rect_y1,
            rect_x2,
            rect_y1 + max(6, int(rect_h * head_ratio))
        )
        head_window = (
            max(0, int(head_window[0])),
            max(0, int(head_window[1])),
            min(mask.shape[1], int(head_window[2])),
            min(mask.shape[0], int(head_window[3]))
        )

        if rect_h >= 20 and head_window[2] > head_window[0] and head_window[3] > head_window[1]:
            head_roi = mask[head_window[1]:head_window[3], head_window[0]:head_window[2]] > 0
            ys, xs = np.where(head_roi)
            if len(xs) >= 4:
                x1 = head_window[0] + xs.min()
                x2 = head_window[0] + xs.max() + 1
                y1 = head_window[1] + ys.min()
                y2 = head_window[1] + ys.max() + 1
                height_ratio = self.get_aim_height_ratio(rect)
                if getattr(self.cfg, 'aim_target_part', 'head') == 'neck':
                    height_ratio = max(height_ratio, 0.72)
                target_y = y1 + (y2 - y1) * min(max(height_ratio, 0.35), 0.82)
                return ((x1 + x2) / 2, target_y), 'simple_head', head_window

        if rect_h >= 18 and head_window[2] > head_window[0] and head_window[3] > head_window[1]:
            ideal = (
                rect_x1 + rect_w / 2,
                rect_y1 + rect_h * min(max(self.get_aim_height_ratio(rect), 0.32), 0.72)
            )
            target_point = self.snap_to_mask_weighted(mask, head_window, ideal, y_weight=2.0)
            if target_point is not None:
                return target_point, 'simple_head', head_window

        return self.visible_color_center(rect, mask), 'simple_visible', rect

    def visible_color_center(self, rect, mask):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        x1 = max(0, int(rect_x1))
        y1 = max(0, int(rect_y1))
        x2 = min(mask.shape[1], int(rect_x2))
        y2 = min(mask.shape[0], int(rect_y2))
        if x2 <= x1 or y2 <= y1:
            return None
        roi = mask[y1:y2, x1:x2] > 0
        ys, xs = np.where(roi)
        if len(xs) == 0:
            return None
        return (float(x1 + np.mean(xs)), float(y1 + np.mean(ys)))

    def choose_simple_candidate(self, candidates, aim_active, pressed_this_frame):
        if not candidates:
            return None
        if not aim_active:
            return candidates[0]

        locked_match = self.find_simple_locked_match(candidates)
        if locked_match is not None and not pressed_this_frame:
            return locked_match
        if self.locked_body is not None and not pressed_this_frame:
            self.miss_locked_target()
            return None

        self.clear_lock()
        return candidates[0]

    def find_simple_locked_match(self, candidates):
        if self.locked_body is None:
            return None

        predicted_center = np.array(self.predicted_locked_body_center(), dtype=float)
        locked_head = self.locked_target['center'] if self.locked_target is not None else predicted_center
        best = None
        best_score = None
        for candidate in candidates:
            body_center = np.array(candidate.get('body_center', self.rect_center(candidate['body_rect'])), dtype=float)
            head_center = np.array(candidate['center'], dtype=float)
            body_distance = float(np.linalg.norm(body_center - predicted_center))
            head_distance = float(np.linalg.norm(head_center - locked_head))
            overlap_bonus = 16 if self.rect_overlap(candidate['body_rect'], self.locked_body) else 0
            score = body_distance + head_distance * 0.45 - overlap_bonus
            if best is None or score < best_score:
                best = candidate
                best_score = score

        if best is None:
            return None

        locked_h = self.locked_body[3] - self.locked_body[1]
        allowed = max(18, locked_h * 0.70)
        if best_score is not None and best_score <= allowed:
            return best
        return None

    def hold_or_miss_simple_lock(self):
        if self.locked_target is None or self.locked_body is None:
            self.miss_locked_target()
            return

        self.miss_locked_target()
        if self.locked_target is None:
            return

        predicted = self.predict_simple_lock_target(np.array(self.locked_target['target'], dtype=float))
        if self.within_aim_fov(predicted):
            self.target = (float(predicted[0]), float(predicted[1]))

    def apply_simple_candidate(self, candidate, lock_target=True):
        target_rect = candidate['rect']
        self.closest_contour = self.rect_to_contour(target_rect)

        if lock_target:
            self.locked_target = candidate
            self.locked_body = candidate.get('body_rect', candidate['rect'])
            self.update_body_track(candidate)
            self.locked_head_window = candidate.get('head_window', self.locked_body)
            self.lock_misses = 0
            x, y = self.predict_simple_lock_target(np.array(candidate['target'], dtype=float))
        else:
            x, y = candidate['target']

        if self.within_aim_fov((x, y)):
            self.target = (float(x), float(y))

    def predict_simple_lock_target(self, measurement):
        if self.track_position is None:
            self.track_position = measurement
            self.track_velocity = np.array((0.0, 0.0), dtype=float)
            self.track_acceleration = np.array((0.0, 0.0), dtype=float)
            self.last_measurement = measurement
            self.filtered_target = (float(measurement[0]), float(measurement[1]))
            return self.filtered_target

        previous_measurement = np.array(self.last_measurement, dtype=float)
        instant_velocity = measurement - previous_measurement
        self.last_measurement = measurement
        instant_speed = float(np.linalg.norm(instant_velocity))
        if instant_speed > 22:
            instant_velocity *= 22 / instant_speed
            instant_speed = 22

        previous_velocity = np.array(self.track_velocity, dtype=float)
        previous_acceleration = np.array(getattr(self, 'track_acceleration', (0.0, 0.0)), dtype=float)
        previous_speed = float(np.linalg.norm(previous_velocity))
        direction_dot = float(np.dot(previous_velocity, instant_velocity))
        direction_agreement = 1.0
        if previous_speed > 0.001 and instant_speed > 0.001:
            direction_agreement = direction_dot / (previous_speed * instant_speed)

        velocity_alpha = 0.34
        if instant_speed > 5:
            velocity_alpha = 0.58
        elif instant_speed > 1.25:
            velocity_alpha = 0.46
        if direction_agreement < -0.20:
            velocity_alpha = 0.72
            previous_velocity *= 0.35

        if instant_speed < 0.35:
            instant_velocity *= 0

        velocity = previous_velocity * (1 - velocity_alpha) + instant_velocity * velocity_alpha
        acceleration_sample = velocity - previous_velocity
        acceleration_len = float(np.linalg.norm(acceleration_sample))
        if acceleration_len > 9:
            acceleration_sample *= 9 / acceleration_len
        acceleration = previous_acceleration * 0.52 + acceleration_sample * 0.48

        residual = measurement - np.array(self.track_position, dtype=float)
        residual_len = float(np.linalg.norm(residual))
        velocity_len = float(np.linalg.norm(velocity))
        consistent_motion = (
            velocity_len > 0.65 and
            float(np.dot(previous_velocity, instant_velocity)) > 0.30
        )

        if residual_len <= 2.25 and not consistent_motion:
            corrected_position = np.array(self.track_position, dtype=float)
            velocity *= 0.25
            acceleration *= 0.20
        else:
            position_alpha = 0.66
            if consistent_motion and velocity_len > 4:
                position_alpha = 0.84
            elif residual_len < 4:
                position_alpha = 0.54
            corrected_position = np.array(self.track_position, dtype=float) + residual * position_alpha

        prediction_strength = self.normalized_prediction_strength()
        motion_scale = min(velocity_len / 7.5, 1.0)
        lead = prediction_strength * (0.10 + motion_scale * 0.62)
        if velocity_len < 0.55 or residual_len < 1.15:
            lead *= 0.20
        elif direction_agreement < 0:
            lead *= 0.55

        predicted = corrected_position + velocity * lead + acceleration * (lead ** 2) * 0.28

        ahead = predicted - measurement
        ahead_len = float(np.linalg.norm(ahead))
        max_ahead = 1.8 + prediction_strength * 5.8 + min(velocity_len, 8.0) * 0.35
        if ahead_len > max_ahead:
            predicted = measurement + ahead * (max_ahead / ahead_len)

        self.track_position = predicted
        self.track_velocity = velocity
        self.track_acceleration = acceleration
        self.filtered_target = (float(predicted[0]), float(predicted[1]))
        return self.filtered_target

    def normalized_prediction_strength(self):
        raw = float(getattr(self.cfg, 'target_prediction', 0.0))
        if raw <= 0:
            return 0.0
        if raw > 1:
            raw /= 5.0
        return float(np.clip(raw, 0.0, 1.0))

    def within_aim_fov(self, target):
        x, y = target
        return -self.aim_fov[0] <= x <= self.aim_fov[0] and -self.aim_fov[1] <= y <= self.aim_fov[1]

    def simple_candidate_score(self, candidate):
        target_x, target_y = candidate['target']
        distance = float(np.hypot(target_x, target_y))
        source_bonus = -12 if candidate.get('source') == 'simple_head' else 10
        confidence = candidate.get('confidence', 0.0)
        model_confidence = candidate.get('model_confidence', 0.0)
        confidence_penalty = (1.0 - confidence) * min(self.aim_fov) * 0.45
        model_penalty = (1.0 - model_confidence) * min(self.aim_fov) * 0.20
        return distance + source_bonus + confidence_penalty + model_penalty

    def apply_candidate(self, candidate, lock_target=True):
        target_rect = candidate['rect']
        self.closest_contour = self.rect_to_contour(target_rect)

        if lock_target:
            self.locked_target = candidate
            self.locked_body = candidate.get('body_rect', candidate['rect'])
            self.update_body_track(candidate)
            self.locked_head_window = candidate.get('head_window', self.get_head_window(self.locked_body))
            self.lock_misses = 0
            if self.locked_body is not None:
                body_h = self.locked_body[3] - self.locked_body[1]
                body_w = self.locked_body[2] - self.locked_body[0]
                if body_h > 0:
                    current_aspect = body_w / float(body_h)
                    self._fall_history.append(current_aspect)
                    if len(self._fall_history) > 6:
                        self._fall_history.pop(0)
            x, y = self.smooth_target(self.stabilize_candidate_target(candidate))
        else:
            x, y = candidate['target']

        if (
                -self.aim_fov[0] <= x <= self.aim_fov[0] and
                -self.aim_fov[1] <= y <= self.aim_fov[1]
        ):
            self.target = (x, y)

    def clear_lock(self):
        self.locked_target = None
        self.locked_body = None
        self.locked_body_center = None
        self.locked_body_velocity = np.array((0.0, 0.0), dtype=float)
        self.locked_head_window = None
        self.stable_head_center = None
        self.lock_misses = 0
        self.filtered_target = None
        self.previous_target = None
        self.last_measurement = None
        self.measurement_velocity = np.array((0.0, 0.0), dtype=float)
        self.track_position = None
        self.track_velocity = (0, 0)
        self.track_acceleration = (0, 0)
        self._fall_history.clear()

    def release_aim_lock(self):
        self.target = None
        self.closest_contour = None
        self.debug_candidates = []
        self.aim_was_active = False
        self.clear_lock()

    def make_body_candidates(self, rect, raw_contours, mask, allow_split=True):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        # #region debug log
        _log("make_body_candidates_RECT", {
            "rect": rect,
            "rect_w": rect_w,
            "rect_h": rect_h,
            "locked_body": self.locked_body
        })
        # #endregion
        if rect_w <= 0 or rect_h <= 0:
            _log("make_body_candidates_REJECT", {"reason": "invalid rect"})
            return []

        area = rect_w * rect_h
        aspect = rect_w / rect_h
        if area > self.fov[0] * self.fov[1] * 0.28:
            _log("make_body_candidates_REJECT", {"reason": "area too large", "area": area})
            return []
        if aspect > 3.4 or aspect < 0.12:
            _log("make_body_candidates_REJECT", {"reason": "aspect ratio", "aspect": aspect})
            return []

        locked_overlap = self.locked_body is not None and self.rect_overlap(rect, self.locked_body)
        locked_near = self.locked_body is not None and self.rect_distance(rect, self.locked_body) <= self.group_distance(rect, self.locked_body)
        locked_continuation = locked_overlap or locked_near

        if self.is_isolated_noise_dot(rect, mask) and not locked_continuation:
            _log("make_body_candidates_REJECT", {"reason": "isolated noise dot"})
            return []
        if self.is_compact_solid_noise(rect, mask) and not locked_continuation:
            _log("make_body_candidates_REJECT", {"reason": "compact solid noise"})
            return []

        model_confidence = self.body_model_confidence(rect, mask)
        if allow_split:
            split_candidates = self.split_wide_body_candidates(rect, raw_contours, mask, model_confidence)
            if split_candidates:
                return split_candidates
            locked_projection = self.make_locked_projection_candidates(rect, raw_contours, mask, locked_continuation)
            if locked_projection:
                return locked_projection

        if self.is_fallen_or_map_noise(rect, mask, model_confidence) and not locked_continuation:
            return []

        if not locked_continuation and self.is_low_quality_new_target(rect, mask, model_confidence):
            return []

        if self.is_exposed_fragment(rect):
            if not locked_continuation and not self.accept_new_exposed_fragment(rect, model_confidence):
                return []
            exposed_candidate = self.make_exposed_candidate(rect, mask)
            if exposed_candidate is not None:
                exposed_candidate['model_confidence'] = model_confidence
            return [exposed_candidate] if exposed_candidate is not None else []

        head_pixels, head_area = self.head_window_pixels(rect, mask)
        head_ratio = head_pixels / max(head_area, 1)
        min_model_confidence = 0.48 if rect_h >= 28 else 0.34
        if model_confidence < min_model_confidence and head_ratio < 0.12 and not locked_continuation:
            return []

        head_roi = self.get_head_roi(rect)
        head_candidates = []
        model_candidate = self.make_head_model_candidate(rect, mask)
        if model_candidate is not None:
            head_candidates.append(model_candidate)
        band_candidate = self.make_head_band_candidate(rect, mask)
        if band_candidate is not None:
            head_candidates.append(band_candidate)
        for contour in raw_contours:
            head_candidates.extend(self.make_head_candidates(contour, head_roi, mask, rect))

        if head_candidates:
            candidates = []
            for head_target in self.prune_head_candidates(head_candidates, rect):
                candidates.append(self.build_body_candidate(rect, head_target, model_confidence))
            return candidates
        else:
            head_roi = self.get_head_roi(rect)
            hx1 = max(0, int(head_roi[0]))
            hy1 = max(0, int(head_roi[1]))
            hx2 = min(mask.shape[1], int(head_roi[2]))
            hy2 = min(mask.shape[0], int(head_roi[3]))
            head_has_color = (hy2 > hy1 and hx2 > hx1 and
                              np.any(mask[hy1:hy2, hx1:hx2] > 0))

            if not head_has_color and rect_h >= 30 and locked_continuation and model_confidence >= 0.50:
                body_center_x = (rect_x1 + rect_x2) / 2
                body_center_y = (rect_y1 + rect_y2) / 2
                head_estimate_y = rect_y1 + rect_h * 0.18
                compensation = (head_estimate_y - body_center_y) * 0.20
                target_point = (body_center_x, body_center_y + compensation)
                target = (target_point[0] - self.fov_center[0], target_point[1] - self.fov_center[1])
                body_only_candidate = {
                    'rect': rect,
                    'target': target,
                    'center': target_point,
                    'source': 'body_only',
                    'score': np.sqrt(target[0]**2 + target[1]**2) + 55
                }
                return [self.build_body_candidate(rect, body_only_candidate, model_confidence * 0.38)]

            if not head_has_color and not locked_continuation:
                return []

            desired = (
                rect_x1 + rect_w / 2,
                rect_y1 + rect_h * self.cfg.head_offset_far
            )
            target_point = self.snap_to_mask(mask, head_roi, desired)
            if target_point is None:
                return []
            head_target = {
                'rect': head_roi,
                'target': (target_point[0] - self.fov_center[0], target_point[1] - self.fov_center[1]),
                'center': target_point,
                'source': 'fallback'
            }
            return [self.build_body_candidate(rect, head_target, model_confidence)]

    def split_wide_body_candidates(self, rect, raw_contours, mask, model_confidence):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        aspect = rect_w / max(rect_h, 1)

        if rect_w < 48 or aspect < 1.65:
            return []
        if model_confidence >= 0.56 and aspect < 2.25:
            return []

        component_rects = []
        for contour in raw_contours:
            x, y, w, h = cv2.boundingRect(contour)
            sub_rect = (x, y, x + w, y + h)
            if not self.rect_overlap(sub_rect, rect):
                continue

            clipped = (
                max(rect_x1, sub_rect[0] - 2),
                max(rect_y1, sub_rect[1] - 2),
                min(rect_x2, sub_rect[2] + 2),
                min(rect_y2, sub_rect[3] + 2)
            )
            clipped_w = clipped[2] - clipped[0]
            clipped_h = clipped[3] - clipped[1]
            if clipped_w <= 0 or clipped_h <= 0:
                continue
            if clipped_w * clipped_h < 120 or clipped_h < 14:
                continue
            if clipped_w > rect_w * 0.78:
                continue
            component_rects.append(clipped)

        if len(component_rects) < 2:
            return []

        component_rects = self.merge_split_components(component_rects)
        if len(component_rects) < 2:
            return []

        candidates = []
        for component_rect in component_rects:
            candidates.extend(self.make_body_candidates(component_rect, raw_contours, mask, allow_split=False))
        return candidates

    @staticmethod
    def merge_split_components(rects):
        rects = sorted(rects, key=lambda item: (item[0], item[1]))
        merged = []
        for rect in rects:
            for index, group in enumerate(merged):
                horizontal_gap = max(rect[0] - group[2], group[0] - rect[2], 0)
                vertical_overlap = max(0, min(rect[3], group[3]) - max(rect[1], group[1]))
                min_height = max(1, min(rect[3] - rect[1], group[3] - group[1]))
                if horizontal_gap <= 2 and vertical_overlap / min_height >= 0.35:
                    merged[index] = (
                        min(group[0], rect[0]),
                        min(group[1], rect[1]),
                        max(group[2], rect[2]),
                        max(group[3], rect[3])
                    )
                    break
            else:
                merged.append(rect)
        return merged

    def make_locked_projection_candidates(self, rect, raw_contours, mask, locked_continuation):
        if not locked_continuation or self.locked_body is None or self.locked_body_center is None:
            return []

        rect_w = rect[2] - rect[0]
        rect_h = rect[3] - rect[1]
        locked_w = self.locked_body[2] - self.locked_body[0]
        locked_h = self.locked_body[3] - self.locked_body[1]
        if locked_w <= 0 or locked_h <= 0:
            return []

        merged_wide = rect_w >= locked_w * 1.35 or rect_w / max(rect_h, 1) >= 1.55
        if not merged_wide:
            return []

        predicted_center = np.array(self.predicted_locked_body_center(), dtype=float)
        if not (
                rect[0] - locked_w * 0.45 <= predicted_center[0] <= rect[2] + locked_w * 0.45 and
                rect[1] - locked_h * 0.45 <= predicted_center[1] <= rect[3] + locked_h * 0.45
        ):
            return []

        center_x = min(max(predicted_center[0], rect[0] + locked_w / 2), rect[2] - locked_w / 2)
        center_y = min(max(predicted_center[1], rect[1] + locked_h / 2), rect[3] - locked_h / 2)
        projected_rect = (
            int(round(center_x - locked_w / 2)),
            int(round(center_y - locked_h / 2)),
            int(round(center_x + locked_w / 2)),
            int(round(center_y + locked_h / 2))
        )

        candidates = self.make_body_candidates(projected_rect, raw_contours, mask, allow_split=False)
        for candidate in candidates:
            candidate['source'] = f"locked-{candidate.get('source', 'projection')}"
            candidate['score'] -= 18
            candidate['confidence'] = max(candidate.get('confidence', 0), 0.82)
        return candidates

    def build_body_candidate(self, body_rect, head_target, model_confidence=0.5):
        rect_x1, rect_y1, rect_x2, rect_y2 = body_rect
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        body_center = (rect_x1 + rect_w / 2, rect_y1 + rect_h / 2)
        body_distance = np.sqrt(
            (body_center[0] - self.fov_center[0])**2 +
            (body_center[1] - self.fov_center[1])**2
        )
        head_distance = np.sqrt(head_target['target'][0]**2 + head_target['target'][1]**2)
        ideal_y = self.estimate_head_center_y(body_rect)
        head_y_penalty = abs(head_target['center'][1] - ideal_y) * 0.85
        score = body_distance + head_distance * 0.20 + head_y_penalty

        return {
            'rect': head_target['rect'],
            'body_rect': body_rect,
            'target': head_target['target'],
            'center': head_target['center'],
            'body_center': body_center,
            'head_window': self.get_head_window(body_rect),
            'source': head_target.get('source', 'unknown'),
            'score': score,
            'confidence': self.candidate_confidence(body_rect, head_target, model_confidence),
            'model_confidence': model_confidence
        }

    def is_exposed_fragment(self, rect):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        area = rect_w * rect_h
        aspect = rect_w / max(rect_h, 1)
        if rect_h < 14 or area < 80:
            return True

        # Small distant full bodies are compact enough to look like one blob.
        # Keep them in the body model path so the aim point is still projected
        # onto the head instead of the middle of the blob.
        if rect_h < 28:
            return aspect > 1.45 or aspect < 0.20

        return False

    def is_isolated_noise_dot(self, rect, mask):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        area = rect_w * rect_h
        if area < 36 or min(rect_w, rect_h) <= 3:
            return True

        if area >= 120 or max(rect_w, rect_h) >= 14:
            return False

        x1 = max(0, int(rect_x1))
        y1 = max(0, int(rect_y1))
        x2 = min(mask.shape[1], int(rect_x2))
        y2 = min(mask.shape[0], int(rect_y2))
        if x2 <= x1 or y2 <= y1:
            return True

        colored = np.count_nonzero(mask[y1:y2, x1:x2] > 0)
        return colored < 42

    def is_compact_solid_noise(self, rect, mask):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        area = rect_w * rect_h
        if area >= 420 or max(rect_w, rect_h) >= 28:
            return False

        x1 = max(0, int(rect_x1))
        y1 = max(0, int(rect_y1))
        x2 = min(mask.shape[1], int(rect_x2))
        y2 = min(mask.shape[0], int(rect_y2))
        if x2 <= x1 or y2 <= y1:
            return True

        roi_area = max((x2 - x1) * (y2 - y1), 1)
        fill_ratio = np.count_nonzero(mask[y1:y2, x1:x2] > 0) / roi_area
        aspect = rect_w / max(rect_h, 1)
        if fill_ratio >= 0.50 and 0.55 <= aspect <= 1.80:
            return True
        if fill_ratio >= 0.38 and aspect >= 0.80 and aspect <= 1.25 and area >= 200 and area <= 600:
            return True

        if fill_ratio >= 0.55 and 0.80 <= aspect <= 1.20 and area >= 160:
            return True
        if fill_ratio >= 0.48 and aspect >= 0.85 and aspect <= 1.15 and area >= 140 and area <= 500:
            return True
        return False

    def is_fallen_or_map_noise(self, rect, mask, model_confidence):
        rect_w = rect[2] - rect[0]
        rect_h = rect[3] - rect[1]
        if rect_w <= 0 or rect_h <= 0:
            return True

        area = rect_w * rect_h
        aspect = rect_w / max(rect_h, 1)
        fill_ratio = self.rect_fill_ratio(rect, mask)
        head_pixels, head_area = self.head_window_pixels(rect, mask)
        head_ratio = head_pixels / max(head_area, 1)

        # Fallen dummy outlines and map/skill strips are usually wide and low.
        if rect_h <= 42 and aspect >= 1.85 and head_ratio < 0.18:
            return True
        if rect_h <= 24 and aspect >= 1.45 and model_confidence < 0.58:
            return True
        if rect_w >= 70 and rect_h <= 20:
            return True

        # Solid map decals tend to be filled blocks, not outline-like bodies.
        if area >= 700 and fill_ratio >= 0.78 and aspect >= 1.20:
            return True
        if area >= 420 and fill_ratio >= 0.55 and 0.65 <= aspect <= 1.55 and model_confidence < 0.55:
            return True
        if area >= 900 and fill_ratio >= 0.50 and head_ratio < 0.22 and model_confidence < 0.42:
            return True

        return False

    def rect_fill_ratio(self, rect, mask):
        x1 = max(0, int(rect[0]))
        y1 = max(0, int(rect[1]))
        x2 = min(mask.shape[1], int(rect[2]))
        y2 = min(mask.shape[0], int(rect[3]))
        if x2 <= x1 or y2 <= y1:
            return 0.0

        area = max((x2 - x1) * (y2 - y1), 1)
        return np.count_nonzero(mask[y1:y2, x1:x2] > 0) / area

    def accept_new_exposed_fragment(self, rect, model_confidence):
        rect_w = rect[2] - rect[0]
        rect_h = rect[3] - rect[1]
        area = rect_w * rect_h
        aspect = rect_w / max(rect_h, 1)

        if area < 140:
            return False
        if model_confidence >= 0.42:
            return True
        if area >= 260 and 0.22 <= aspect <= 1.35 and model_confidence >= 0.30:
            return True
        return False

    def is_low_quality_new_target(self, rect, mask, model_confidence):
        rect_w = rect[2] - rect[0]
        rect_h = rect[3] - rect[1]
        area = rect_w * rect_h
        if area < 110:
            return True

        if model_confidence >= 0.52:
            return False

        head_pixels, head_area = self.head_window_pixels(rect, mask)
        head_ratio = head_pixels / max(head_area, 1)
        if head_ratio < 0.055:
            return True

        if rect_h >= 28 and model_confidence < 0.38 and head_ratio < 0.18:
            return True

        return False

    def body_model_confidence(self, rect, mask):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        if rect_w <= 0 or rect_h <= 0:
            return 0.0

        x1 = max(0, int(rect_x1))
        y1 = max(0, int(rect_y1))
        x2 = min(mask.shape[1], int(rect_x2))
        y2 = min(mask.shape[0], int(rect_y2))
        if x2 <= x1 or y2 <= y1:
            return 0.0

        roi = mask[y1:y2, x1:x2]
        pixels = roi > 0
        colored = int(np.count_nonzero(pixels))
        area = max(rect_w * rect_h, 1)
        if colored == 0:
            return 0.0

        fill_ratio = colored / area
        aspect = rect_w / max(rect_h, 1)
        row_activity = np.count_nonzero(pixels, axis=1) / max(rect_w, 1)
        col_activity = np.count_nonzero(pixels, axis=0) / max(rect_h, 1)

        row_count = len(row_activity)
        col_count = len(col_activity)
        top_end = min(row_count, max(1, int(rect_h * 0.30)))
        mid_end = min(row_count, max(top_end + 1, int(rect_h * 0.68)))
        top_strength = self.safe_mean(row_activity[:top_end])
        mid_strength = self.safe_mean(row_activity[top_end:mid_end]) if mid_end > top_end else 0.0
        low_strength = self.safe_mean(row_activity[mid_end:]) if row_count > mid_end else 0.0

        mid_col = min(col_count, max(1, rect_w // 2))
        left_strength = self.safe_mean(col_activity[:mid_col])
        right_strength = self.safe_mean(col_activity[mid_col:]) if col_count > mid_col else left_strength
        symmetry = 1.0 - min(abs(left_strength - right_strength) / max(left_strength + right_strength, 0.01), 1.0)

        if rect_h < 28:
            aspect_score = self.score_range(aspect, 0.28, 1.20, 0.52)
            fill_score = self.score_range(fill_ratio, 0.08, 0.72, 0.34)
            vertical_score = min(1.0, (top_strength * 1.25 + mid_strength * 0.85) / 0.55)
            size_score = min(max(rect_h / 24, 0.45), 1.0)
        else:
            aspect_score = self.score_range(aspect, 0.18, 1.05, 0.46)
            fill_score = self.score_range(fill_ratio, 0.035, 0.46, 0.16)
            vertical_score = min(1.0, (top_strength * 1.25 + mid_strength + low_strength * 0.55) / 0.72)
            size_score = min(max(rect_h / 70, 0.45), 1.0)

        head_window = self.get_head_window(rect)
        hx1 = max(0, int(head_window[0]))
        hy1 = max(0, int(head_window[1]))
        hx2 = min(mask.shape[1], int(head_window[2]))
        hy2 = min(mask.shape[0], int(head_window[3]))
        if hx2 > hx1 and hy2 > hy1:
            head_pixels = np.count_nonzero(mask[hy1:hy2, hx1:hx2] > 0)
            head_ratio = head_pixels / max((hx2 - hx1) * (hy2 - hy1), 1)
            head_score = min(head_ratio / 0.18, 1.0)
        else:
            head_score = 0.0

        blob_penalty = 0.0
        if fill_ratio > 0.56 and rect_h >= 28:
            blob_penalty += min((fill_ratio - 0.56) * 1.8, 0.48)
        if 0.72 <= aspect <= 1.35 and fill_ratio > 0.42 and rect_h >= 22:
            blob_penalty += min((fill_ratio - 0.42) * 0.9, 0.28)
        if aspect > 1.65:
            blob_penalty += min((aspect - 1.65) * 0.22, 0.25)

        outline_penalty = 0.0
        outline_score = 0.0
        if rect_h >= 20:
            for contour in self._get_contours_in_rect(mask, rect):
                contour_area = float(cv2.contourArea(contour))
                if contour_area > 0:
                    arc_len = cv2.arcLength(contour, True)
                    outline_ratio = arc_len / max(contour_area, 1.0)
                    outline_score = max(outline_score, outline_ratio)
                    if outline_ratio < 3.2:
                        outline_penalty += min((3.2 - outline_ratio) * 0.28, 0.38)

        confidence = (
            aspect_score * 0.20 +
            fill_score * 0.16 +
            vertical_score * 0.22 +
            head_score * 0.22 +
            symmetry * 0.10 +
            size_score * 0.10 -
            blob_penalty -
            outline_penalty
        )

        if outline_score > 0 and outline_score < 4.5 and fill_ratio > 0.42 and rect_h >= 28:
            confidence -= 0.18

        if fill_ratio > 0.55 and 0.80 <= aspect <= 1.25 and area >= 160 and area <= 800:
            confidence -= 0.22

        return float(np.clip(confidence, 0.0, 1.0))

    def head_window_pixels(self, rect, mask):
        head_window = self.get_head_window(rect)
        hx1 = max(0, int(head_window[0]))
        hy1 = max(0, int(head_window[1]))
        hx2 = min(mask.shape[1], int(head_window[2]))
        hy2 = min(mask.shape[0], int(head_window[3]))
        if hx2 <= hx1 or hy2 <= hy1:
            return 0, 0

        area = (hx2 - hx1) * (hy2 - hy1)
        pixels = np.count_nonzero(mask[hy1:hy2, hx1:hx2] > 0)
        return int(pixels), int(area)

    def make_exposed_candidate(self, rect, mask):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        desired = ((rect_x1 + rect_x2) / 2, (rect_y1 + rect_y2) / 2)
        target_point = self.snap_to_mask(mask, rect, desired)
        if target_point is None:
            return None

        target = (target_point[0] - self.fov_center[0], target_point[1] - self.fov_center[1])
        distance = np.sqrt(target[0]**2 + target[1]**2)
        return {
            'rect': rect,
            'body_rect': rect,
            'target': target,
            'center': target_point,
            'body_center': target_point,
            'source': 'exposed',
            'score': distance,
            'exposed': True
        }

    def prune_head_candidates(self, head_candidates, body_rect):
        body_center_x = (body_rect[0] + body_rect[2]) / 2
        head_candidates = sorted(head_candidates, key=lambda candidate: self.rank_head_candidate(candidate, body_rect))
        kept = []
        for candidate in head_candidates:
            center_x = candidate['center'][0]
            if all(abs(center_x - item['center'][0]) > 6 for item in kept):
                kept.append(candidate)
        return kept or head_candidates[:1]

    def rank_head_candidate(self, candidate, body_rect):
        rect_x1, rect_y1, rect_x2, rect_y2 = body_rect
        body_center_x = (rect_x1 + rect_x2) / 2
        center_x, center_y = candidate['center']
        ideal_y = self.estimate_head_center_y(body_rect)
        return (
            abs(center_x - body_center_x) * 0.65 +
            abs(candidate['target'][0]) * 0.22 +
            abs(center_y - ideal_y) * 0.95 +
            candidate.get('score', 0) * 0.08
        )

    def get_head_roi(self, rect):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_h = rect_y2 - rect_y1
        if rect_h < 28:
            roi_h = max(6, int(rect_h * 0.58))
            return (rect_x1, rect_y1, rect_x2, min(rect_y2, rect_y1 + roi_h))

        roi_h = max(8, int(rect_h * self.get_head_roi_ratio(rect)))
        return (rect_x1, rect_y1, rect_x2, min(rect_y2, rect_y1 + roi_h))

    def get_head_window(self, rect):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        center_x = (rect_x1 + rect_x2) / 2
        center_y = self.estimate_head_center_y(rect)
        if rect_h < 28:
            half_w = max(4, min(14, rect_w * 0.42))
            half_h = max(3, min(8, rect_h * 0.16))
        else:
            half_w = max(7, min(26, rect_w * (0.34 if rect_h >= 42 else 0.46)))
            half_h = max(5, min(18, rect_h * (0.10 if rect_h >= 42 else 0.16)))
        return (
            max(rect_x1, center_x - half_w),
            max(rect_y1, center_y - half_h),
            min(rect_x2, center_x + half_w),
            min(rect_y2, center_y + half_h)
        )

    def get_head_roi_ratio(self, rect):
        rect_h = rect[3] - rect[1]
        if rect_h >= 82:
            return min(self.cfg.head_roi_ratio, 0.30)
        if rect_h >= 42:
            return max(self.cfg.head_roi_ratio, 0.34)
        return 0.46

    def get_aim_height_ratio(self, rect):
        rect_h = rect[3] - rect[1]
        if rect_h >= 82:
            value = getattr(self.cfg, 'aim_height_near', getattr(self.cfg, 'head_offset_near', 0.50))
        elif rect_h >= 42:
            value = getattr(self.cfg, 'aim_height_mid', getattr(self.cfg, 'head_offset_mid', 0.55))
        else:
            value = getattr(self.cfg, 'aim_height_far', getattr(self.cfg, 'head_offset_far', 0.65))
        return float(min(max(value, 0.0), 1.0))

    def min_color_confidence(self, source='simple_visible'):
        threshold = float(getattr(self.cfg, 'color_confidence', 0.62))
        if source == 'simple_head':
            return max(0.35, threshold - 0.10)
        return threshold

    def simple_confidence(self, source, model_confidence, rect, fill_ratio):
        rect_w = rect[2] - rect[0]
        rect_h = rect[3] - rect[1]
        aspect = rect_w / max(rect_h, 1)
        size_score = min(max(rect_h / 42, 0.25), 1.0)
        aspect_score = self.score_range(aspect, 0.12, 3.2, 0.58)

        if source == 'simple_head':
            source_score = 0.88
        else:
            source_score = 0.48

        fill_score = 1.0 - min(max(fill_ratio - 0.10, 0.0) / 0.55, 1.0) * 0.35
        confidence = (
            source_score * 0.34 +
            model_confidence * 0.38 +
            size_score * 0.14 +
            aspect_score * 0.08 +
            fill_score * 0.06
        )
        if source == 'simple_head':
            confidence = max(confidence, 0.78)
        return float(np.clip(confidence, 0.0, 1.0))

    def estimate_head_center_y(self, rect):
        rect_y1 = rect[1]
        rect_h = rect[3] - rect[1]
        offset = self.get_aim_height_ratio(rect)
        part = getattr(self.cfg, 'aim_target_part', 'head')
        if part == 'neck':
            offset = max(offset, 0.72)
        elif part == 'body':
            offset = max(offset, 0.50)
        return rect_y1 + rect_h * offset

    def make_head_model_candidate(self, rect, mask):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        if rect_w <= 0 or rect_h <= 0:
            return None

        head_window = self.get_head_window(rect)
        ideal = (
            rect_x1 + rect_w / 2,
            self.estimate_head_center_y(rect)
        )
        target_point = self.snap_to_mask_weighted(mask, head_window, ideal, y_weight=2.0)
        if target_point is None:
            target_point = ideal

        target = (target_point[0] - self.fov_center[0], target_point[1] - self.fov_center[1])
        distance = np.sqrt(target[0]**2 + target[1]**2)
        far_bonus = 42 if rect_h < 28 else 28 if rect_h < 42 else 8
        return {
            'rect': head_window,
            'target': target,
            'center': target_point,
            'source': 'model',
            'score': distance - far_bonus
        }

    def make_head_band_candidate(self, rect, mask):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        if rect_w <= 0 or rect_h <= 0:
            return None

        ideal = (
            rect_x1 + rect_w / 2,
            self.estimate_head_center_y(rect)
        )
        band = self.get_head_window(rect)
        target_point = self.find_best_head_blob(mask, band, ideal, rect)
        if target_point is None:
            target_point = self.snap_to_mask_weighted(mask, band, ideal, y_weight=1.9)
        if target_point is None:
            return None

        target = (target_point[0] - self.fov_center[0], target_point[1] - self.fov_center[1])
        return {
            'rect': (
                max(rect_x1, target_point[0] - 4),
                max(rect_y1, target_point[1] - 4),
                min(rect_x2, target_point[0] + 4),
                min(rect_y2, target_point[1] + 4)
            ),
            'target': target,
            'center': target_point,
            'source': 'band',
            'score': np.sqrt(target[0]**2 + target[1]**2) - 18
        }

    def find_best_head_blob(self, mask, band, ideal, body_rect):
        band_x1, band_y1, band_x2, band_y2 = band
        band_x1 = max(0, int(band_x1))
        band_y1 = max(0, int(band_y1))
        band_x2 = min(mask.shape[1], int(band_x2))
        band_y2 = min(mask.shape[0], int(band_y2))
        if band_x2 <= band_x1 or band_y2 <= band_y1:
            return None

        roi = mask[band_y1:band_y2, band_x1:band_x2]
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(roi, 8)
        if num_labels <= 1:
            return None

        body_w = body_rect[2] - body_rect[0]
        body_h = body_rect[3] - body_rect[1]
        ideal_x, ideal_y = ideal
        x_allow = max(10, min(body_w * 0.46, 34))
        y_allow = max(6, body_h * 0.13)
        best_point = None
        best_score = float('inf')

        for label in range(1, num_labels):
            area = stats[label, cv2.CC_STAT_AREA]
            width = stats[label, cv2.CC_STAT_WIDTH]
            height = stats[label, cv2.CC_STAT_HEIGHT]
            if area < 2 or width <= 0 or height <= 0:
                continue

            cx = band_x1 + float(centroids[label][0])
            cy = band_y1 + float(centroids[label][1])
            if abs(cx - ideal_x) > x_allow and body_h >= 42:
                continue
            if cy > ideal_y + y_allow:
                continue

            aspect = width / max(height, 1)
            if width > max(28, body_w * 0.45):
                ys, xs = np.where(labels == label)
                abs_xs = band_x1 + xs.astype(float)
                abs_ys = band_y1 + ys.astype(float)
                keep = (
                    (np.abs(abs_xs - ideal_x) <= x_allow) &
                    (abs_ys <= ideal_y + y_allow)
                )
                if np.any(keep):
                    abs_xs = abs_xs[keep]
                    abs_ys = abs_ys[keep]
                    distances = (
                        (abs_xs - ideal_x) ** 2 +
                        ((abs_ys - ideal_y) * 1.8) ** 2
                    )
                    best_index = int(np.argmin(distances))
                    cx = float(abs_xs[best_index])
                    cy = float(abs_ys[best_index])
                else:
                    continue

            shape_penalty = max(0, aspect - 2.4) * 8
            score = (
                abs(cx - ideal_x) * 0.55 +
                abs(cy - ideal_y) * 1.35 +
                shape_penalty -
                min(area, 120) * 0.08
            )
            if score < best_score:
                best_score = score
                best_point = (cx, cy)

        return best_point

    def should_refresh_debug(self):
        interval = max(getattr(self.cfg, 'debug_refresh_interval', 1), 1)
        self.debug_frame = (self.debug_frame + 1) % interval
        return self.debug_frame == 0

    def choose_body_candidate(self, candidates, aim_active, pressed_this_frame):
        # #region debug log
        _log("choose_body_candidate_START", {
            "candidates_count": len(candidates),
            "aim_active": aim_active,
            "pressed_this_frame": pressed_this_frame,
            "locked_body": self.locked_body
        })
        # #endregion

        candidates = sorted(candidates, key=lambda candidate: self.selection_score(candidate))
        if not aim_active:
            # #region debug log
            _log("choose_body_candidate_NOT_AIM_ACTIVE", {"return": "candidates[0]"})
            # #endregion
            return candidates[0]

        if pressed_this_frame or self.locked_body is None:
            self.lock_misses = 0
            # #region debug log
            _log("choose_body_candidate_NEW_TARGET", {"return": "candidates[0]"})
            # #endregion
            return candidates[0]

        locked_match = self.find_locked_body_match(candidates)
        if locked_match is not None:
            # #region debug log
            _log("choose_body_candidate_LOCKED_MATCH", {"return": "locked_match"})
            # #endregion
            return locked_match

        self.miss_locked_target()
        # #region debug log
        _log("choose_body_candidate_MISS", {"lock_misses": self.lock_misses, "locked_body": self.locked_body})
        # #endregion
        if self.locked_body is None:
            # #region debug log
            _log("choose_body_candidate_FALLBACK", {"return": "candidates[0]"})
            # #endregion
            return candidates[0]

        # Keep the sticky lock from jumping to unrelated candidates when several
        # target-colored blobs are inside FOV. A new target is allowed only after
        # the current lock has missed for enough frames and clears itself.
        return None

    def find_locked_body_match(self, candidates):
        if self.locked_body is None:
            return None

        locked_center = self.predicted_locked_body_center()
        locked_head_center = self.locked_target['center'] if self.locked_target is not None else None
        best_match = None
        best_distance = float('inf')
        for candidate in candidates:
            body_rect = candidate['body_rect']
            body_center = candidate['body_center']
            body_distance = np.sqrt(
                (body_center[0] - locked_center[0])**2 +
                (body_center[1] - locked_center[1])**2
            )
            head_distance = np.sqrt(
                (candidate['center'][0] - locked_head_center[0])**2 +
                (candidate['center'][1] - locked_head_center[1])**2
            ) if locked_head_center is not None else 0
            overlap = self.rect_overlap_ratio(body_rect, self.locked_body)
            continuity_limit = max(34, min(92, (self.locked_body[3] - self.locked_body[1]) * 0.95))
            # #region debug log
            _log("find_locked_body_match_CANDIDATE", {
                "body_distance": body_distance,
                "continuity_limit": continuity_limit,
                "overlap": overlap,
                "skip": overlap <= 0 and body_distance > continuity_limit
            })
            # #endregion
            if overlap <= 0 and body_distance > continuity_limit:
                continue

            confidence_bonus = candidate.get('confidence', 0) * 12 + candidate.get('model_confidence', 0) * 10
            distance = body_distance * 0.82 + head_distance * 0.44 - overlap * 48 - confidence_bonus
            if self.locked_head_window is not None:
                current_head_window = candidate.get('head_window', self.get_head_window(body_rect))
                distance -= self.rect_overlap_ratio(current_head_window, self.locked_head_window) * 24

            if distance < best_distance:
                best_distance = distance
                best_match = candidate

        return best_match

    def update_body_track(self, candidate):
        body_center = np.array(candidate['body_center'], dtype=float)
        if self.locked_body_center is None:
            self.locked_body_center = body_center
            self.locked_body_velocity = np.array((0.0, 0.0), dtype=float)
            return

        delta = body_center - self.locked_body_center
        delta_len = float(np.linalg.norm(delta))
        if delta_len > 28:
            delta *= 28 / delta_len

        alpha = 0.55 if delta_len > 4 else 0.32
        self.locked_body_velocity = self.locked_body_velocity * (1 - alpha) + delta * alpha
        self.locked_body_center = body_center

    def predicted_locked_body_center(self):
        if self.locked_body_center is not None:
            return tuple(self.locked_body_center + self.locked_body_velocity * 0.85)
        return self.rect_center(self.locked_body)

    def stabilize_candidate_target(self, candidate):
        center = np.array(candidate['center'], dtype=float)
        if self.stable_head_center is None:
            self.stable_head_center = center
        else:
            delta = center - self.stable_head_center
            delta_len = float(np.linalg.norm(delta))
            source = candidate.get('source', 'unknown')
            body_rect = candidate.get('body_rect', candidate.get('rect'))
            body_h = body_rect[3] - body_rect[1]
            body_w = body_rect[2] - body_rect[0]

            speed = float(np.linalg.norm(self.measurement_velocity)) if hasattr(self, 'measurement_velocity') else 0
            jump_limit = max(5.5, min(18.0, body_h * 0.22))
            if speed > 8:
                jump_limit = max(jump_limit, body_h * 0.30)
            elif speed > 4:
                jump_limit = max(jump_limit, body_h * 0.26)

            if (
                    delta_len > jump_limit and
                    candidate.get('confidence', 0) < 0.72 and
                    source not in ('model', 'fallback')
            ):
                center = self.stable_head_center + delta / delta_len * jump_limit
                delta = center - self.stable_head_center
                delta_len = float(np.linalg.norm(delta))

            blend = 0.5
            if delta_len < 0.75:
                center = self.stable_head_center
            elif delta_len < 3.0 and source in ('contour', 'band', 'split'):
                center = self.stable_head_center * 0.68 + center * 0.32
            else:
                if source in ('model', 'fallback'):
                    blend = 0.72
                elif candidate.get('confidence', 0) < 0.62:
                    blend = 0.46
                else:
                    blend = 0.58
                center = self.stable_head_center * (1 - blend) + center * blend

            if len(self._fall_history) >= 3:
                oldest = self._fall_history[0]
                newest = self._fall_history[-1]
                if oldest > 0.35 and newest < oldest * 0.50:
                    center = self.stable_head_center * 0.88 + center * 0.12
                elif oldest > 0.38 and newest < oldest * 0.55:
                    center = self.stable_head_center * 0.94 + center * 0.06

            if body_h < 35:
                blend *= 0.60
            elif body_h < 55:
                blend *= 0.80

            if body_h > 0 and len(self._fall_history) >= 3:
                current_aspect = body_w / float(body_h)
                oldest = self._fall_history[0]
                if oldest > 0.38 and current_aspect < oldest * 0.55:
                    blend *= 0.45

            if body_h < 35 and source in ('contour', 'band', 'exposed'):
                blend *= 0.55
            elif 35 <= body_h <= 45 and source in ('contour', 'band', 'exposed'):
                blend *= 0.72

            self.stable_head_center = center

        target = (
            float(center[0] - self.fov_center[0]),
            float(center[1] - self.fov_center[1])
        )
        if self.locked_head_window is not None:
            target = self.clamp_target_to_window(target, self.locked_head_window)
            return (float(target[0]), float(target[1]))
        return target

    def selection_score(self, candidate):
        return (
            candidate['score'] -
            candidate.get('confidence', 0) * 16 -
            candidate.get('model_confidence', 0) * 12
        )

    def candidate_confidence(self, body_rect, head_target, model_confidence=0.5):
        rect_h = body_rect[3] - body_rect[1]
        source = head_target.get('source', 'unknown')
        source_score = {
            'model': 0.92,
            'band': 0.86,
            'contour': 0.78,
            'split': 0.66,
            'fallback': 0.58,
            'exposed': 0.42,
            'body_only': 0.38
        }.get(source, 0.50)
        ideal_y = self.estimate_head_center_y(body_rect)
        y_error = abs(head_target['center'][1] - ideal_y) / max(rect_h, 1)
        head_score = max(0.0, 1.0 - y_error * 4.2)
        size_score = min(max(rect_h / 36, 0.35), 1.0)
        return source_score * 0.34 + head_score * 0.26 + size_score * 0.12 + model_confidence * 0.28

    @staticmethod
    def score_range(value, low, high, ideal):
        if value <= low or value >= high:
            return 0.0
        if value == ideal:
            return 1.0
        if value < ideal:
            return (value - low) / max(ideal - low, 0.001)
        return (high - value) / max(high - ideal, 0.001)

    @staticmethod
    def safe_mean(values):
        if len(values) == 0:
            return 0.0
        return float(np.mean(values))

    def snap_to_mask(self, mask, rect, desired):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_x1 = max(0, int(rect_x1))
        rect_y1 = max(0, int(rect_y1))
        rect_x2 = min(mask.shape[1], int(rect_x2))
        rect_y2 = min(mask.shape[0], int(rect_y2))
        if rect_x2 <= rect_x1 or rect_y2 <= rect_y1:
            return None

        roi = mask[rect_y1:rect_y2, rect_x1:rect_x2]
        points = cv2.findNonZero(roi)
        if points is None:
            return None

        desired_x = desired[0] - rect_x1
        desired_y = desired[1] - rect_y1
        points = points.reshape(-1, 2)
        distances = (points[:, 0] - desired_x) ** 2 + (points[:, 1] - desired_y) ** 2
        closest = points[int(np.argmin(distances))]
        return (rect_x1 + float(closest[0]), rect_y1 + float(closest[1]))

    def snap_to_mask_weighted(self, mask, rect, desired, x_weight=1.0, y_weight=1.0):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_x1 = max(0, int(rect_x1))
        rect_y1 = max(0, int(rect_y1))
        rect_x2 = min(mask.shape[1], int(rect_x2))
        rect_y2 = min(mask.shape[0], int(rect_y2))
        if rect_x2 <= rect_x1 or rect_y2 <= rect_y1:
            return None

        roi = mask[rect_y1:rect_y2, rect_x1:rect_x2]
        points = cv2.findNonZero(roi)
        if points is None:
            return None

        desired_x = desired[0] - rect_x1
        desired_y = desired[1] - rect_y1
        points = points.reshape(-1, 2)
        distances = (
            ((points[:, 0] - desired_x) * x_weight) ** 2 +
            ((points[:, 1] - desired_y) * y_weight) ** 2
        )
        closest = points[int(np.argmin(distances))]
        return (rect_x1 + float(closest[0]), rect_y1 + float(closest[1]))

    def clamp_target_to_window(self, target, window):
        x = float(target[0] + self.fov_center[0])
        y = float(target[1] + self.fov_center[1])
        x = min(max(x, window[0]), window[2])
        y = min(max(y, window[1]), window[3])
        return np.array((x - self.fov_center[0], y - self.fov_center[1]), dtype=float)

    def make_head_candidates(self, contour, head_roi=None, mask=None, body_rect=None):
        rect_x, rect_y, rect_w, rect_h = cv2.boundingRect(contour)
        rect = (rect_x, rect_y, rect_x + rect_w, rect_y + rect_h)
        if head_roi is not None and not self.rect_overlap(rect, head_roi):
            return []

        if body_rect is not None:
            ideal_y = self.estimate_head_center_y(body_rect)
            allowed_low = ideal_y + max(7, (body_rect[3] - body_rect[1]) * 0.10)
            if rect_y + rect_h / 2 > allowed_low:
                return []

        if (
                rect_h <= 20 and
                rect_w > max(24, rect_h * 1.9) and
                body_rect is not None and
                rect_y <= self.estimate_head_center_y(body_rect) + max(4, rect_h * 0.5)
        ):
            return self.split_wide_head_candidate(rect, head_roi, mask)

        candidate = self.make_head_candidate(contour, head_roi, mask, body_rect)
        return [candidate] if candidate is not None else []

    def split_wide_head_candidate(self, rect, head_roi, mask):
        if mask is None:
            return []

        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        estimated_width = max(rect_h * 1.05, 8)
        count = int(np.clip(round(rect_w / estimated_width), 2, 4))
        candidates = []

        for index in range(count):
            seg_x1 = int(rect_x1 + rect_w * index / count)
            seg_x2 = int(rect_x1 + rect_w * (index + 1) / count)
            seg_rect = (
                max(seg_x1, head_roi[0] if head_roi is not None else seg_x1),
                max(rect_y1, head_roi[1] if head_roi is not None else rect_y1),
                min(seg_x2, head_roi[2] if head_roi is not None else seg_x2),
                min(rect_y2, head_roi[3] if head_roi is not None else rect_y2)
            )
            if seg_rect[2] <= seg_rect[0] or seg_rect[3] <= seg_rect[1]:
                continue

            desired = ((seg_rect[0] + seg_rect[2]) / 2, seg_rect[1] + (seg_rect[3] - seg_rect[1]) * 0.64)
            target_point = desired

            target = (target_point[0] - self.fov_center[0], target_point[1] - self.fov_center[1])
            area = (seg_rect[2] - seg_rect[0]) * (seg_rect[3] - seg_rect[1])
            candidates.append({
                'rect': seg_rect,
                'target': target,
                'center': target_point,
                'source': 'split',
                'score': np.sqrt(target[0]**2 + target[1]**2) - min(area, 180) * 0.01
            })

        return candidates

    def make_head_candidate(self, contour, head_roi=None, mask=None, body_rect=None):
        rect_x, rect_y, rect_w, rect_h = cv2.boundingRect(contour)
        rect = (rect_x, rect_y, rect_x + rect_w, rect_y + rect_h)
        if head_roi is not None and not self.rect_overlap(rect, head_roi):
            return None

        area = rect_w * rect_h
        if area < 8 or area > 900:
            return None

        aspect = rect_w / max(rect_h, 1)
        if not 0.45 <= aspect <= 1.75:
            return None

        if rect_w > 34 or rect_h > 34:
            return None

        # Use contour moments to get the true geometric centroid of the
        # head color block (works correctly for both filled and hollow rings).
        M = cv2.moments(contour)
        if M['m00'] > 0:
            center_x = M['m10'] / M['m00']
            center_y = M['m01'] / M['m00']
        else:
            center_x = rect_x + rect_w / 2
            center_y = rect_y + rect_h / 2

        if body_rect is not None:
            ideal_y = self.estimate_head_center_y(body_rect)
            allowed_low = ideal_y + max(7, (body_rect[3] - body_rect[1]) * 0.10)
            if center_y > allowed_low:
                return None

        target = (center_x - self.fov_center[0], center_y - self.fov_center[1])
        distance = np.sqrt(target[0]**2 + target[1]**2)

        # Favor compact head markers over random purple map details.
        compact_bonus = min(rect_w, rect_h) / max(rect_w, rect_h, 1)
        score = distance - compact_bonus * 10
        return {
            'rect': rect,
            'target': target,
            'center': (center_x, center_y),
            'source': 'contour',
            'score': score
        }

    def miss_locked_target(self):
        self.lock_misses += 1

        if self.locked_body is not None:
            body_h = self.locked_body[3] - self.locked_body[1]
            body_w = self.locked_body[2] - self.locked_body[0]
            if body_h > 0:
                current_aspect = body_w / float(body_h)
                self._fall_history.append(current_aspect)
                if len(self._fall_history) > 6:
                    self._fall_history.pop(0)

                if len(self._fall_history) >= 3:
                    oldest = self._fall_history[0]
                    newest = self._fall_history[-1]
                    if oldest > 0.35 and newest < oldest * 0.50:
                        self.lock_misses = max(self.lock_misses, self.cfg.target_lock_frames)
                    elif oldest > 0.38 and newest < oldest * 0.55:
                        self.lock_misses = max(self.lock_misses, self.cfg.target_lock_frames // 2)

        if self.lock_misses > self.cfg.target_lock_frames:
            self.clear_lock()

    def smooth_target(self, target):
        return self.predict_simple_lock_target(np.array(target, dtype=float))

    @staticmethod
    def rect_distance(a, b):
        horizontal_gap = max(a[0] - b[2], b[0] - a[2], 0)
        vertical_gap = max(a[1] - b[3], b[1] - a[3], 0)
        return np.sqrt(horizontal_gap**2 + vertical_gap**2)

    @staticmethod
    def rect_overlap(a, b):
        return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])

    @staticmethod
    def rect_overlap_ratio(a, b):
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        if x2 <= x1 or y2 <= y1:
            return 0

        intersection = (x2 - x1) * (y2 - y1)
        area_a = max((a[2] - a[0]) * (a[3] - a[1]), 1)
        area_b = max((b[2] - b[0]) * (b[3] - b[1]), 1)
        return intersection / min(area_a, area_b)

    @staticmethod
    def rect_center(rect):
        return ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)

    def _get_contours_in_rect(self, mask, rect):
        x1 = max(0, int(rect[0]))
        y1 = max(0, int(rect[1]))
        x2 = min(mask.shape[1], int(rect[2]))
        y2 = min(mask.shape[0], int(rect[3]))
        if x2 <= x1 or y2 <= y1:
            return []
        roi = mask[y1:y2, x1:x2]
        contours_result = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if len(contours_result) == 3:
            _, contours, _ = contours_result
        else:
            contours, _ = contours_result
        return contours

    @staticmethod
    def group_distance(a, b):
        avg_height = ((a[3] - a[1]) + (b[3] - b[1])) / 2
        return max(10, min(24, avg_height * 0.35))

    @staticmethod
    def rect_to_contour(rect):
        rect_x1, rect_y1, rect_x2, rect_y2 = rect
        return np.array(
            [
                [[rect_x1, rect_y1]],
                [[rect_x2, rect_y1]],
                [[rect_x2, rect_y2]],
                [[rect_x1, rect_y2]]
            ],
            dtype=np.int32
        )

    @staticmethod
    def get_region(region, recoil_offset):
        region = (
            region[0],
            region[1] - recoil_offset,
            region[2],
            region[3] - recoil_offset
        )
        return region

    def run_debug_window(self, recoil_offset):
        if self.display_mode == 'game':
            debug_img = self.img
        else:
            debug_img = self.thresh
            debug_img = cv2.cvtColor(debug_img, cv2.COLOR_GRAY2BGR)

        # Draw line to the closest target
        if self.target is not None:
            target_point = (
                int(self.target[0] + self.fov_center[0]),
                int(self.target[1] + self.fov_center[1])
            )
            debug_img = cv2.line(
                debug_img,
                self.fov_center,
                target_point,
                (0, 255, 0),
                2
            )
            debug_img = cv2.circle(
                debug_img,
                target_point,
                3,
                (255, 0, 255),
                -1
            )

        for candidate in self.debug_candidates:
            target_x, target_y = candidate['target']
            color = self.debug_source_color(candidate.get('source'))
            debug_img = cv2.circle(
                debug_img,
                (int(target_x + self.fov_center[0]), int(target_y + self.fov_center[1])),
                2,
                color,
                1
            )

        # Draw rectangle around closest target
        if self.closest_contour is not None:
            x, y, w, h = cv2.boundingRect(self.closest_contour)
            debug_img = cv2.rectangle(
                debug_img,
                (x, y),
                (x + w, y + h),
                (0, 0, 255),
                2
            )

        # Draw FOV, a green rectangle
        debug_img = cv2.rectangle(
            debug_img,
            (0, 0),
            (self.fov[0], self.fov[1]),
            (0, 255, 0),
            2
        )

        # Draw the capture-center crosshair on the FOV crop. Avoid grabbing and
        # resizing a full-screen frame from the debug path; that stalls 240Hz aim.
        debug_img = cv2.rectangle(
            debug_img,
            (self.fov_center[0] - 5, self.fov_center[1] - 5),
            (self.fov_center[0] + 5, self.fov_center[1] + 5),
            (255, 255, 255),
            1
        )
        debug_img = cv2.resize(debug_img, self.window_resolution)
        cv2.imshow(self.window_name, debug_img)
        self.position_debug_window()
        cv2.waitKey(1)

    def position_debug_window(self):
        if not getattr(self.cfg, 'debug', False):
            return
        try:
            cv2.resizeWindow(self.window_name, self.window_resolution[0], self.window_resolution[1])
            cv2.moveWindow(self.window_name, 0, max(0, self.screen[1] - self.window_resolution[1]))
            if hasattr(cv2, 'WND_PROP_TOPMOST'):
                cv2.setWindowProperty(self.window_name, cv2.WND_PROP_TOPMOST, 1)
        except cv2.error:
            pass

    @staticmethod
    def debug_source_color(source):
        colors = {
            'model': (255, 180, 0),
            'band': (255, 255, 0),
            'contour': (0, 255, 255),
            'split': (0, 165, 255),
            'exposed': (255, 0, 255),
            'fallback': (180, 180, 180)
        }
        return colors.get(source, (255, 255, 255))
