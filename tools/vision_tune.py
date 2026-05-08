import itertools
import os
import sys
from dataclasses import dataclass
from types import SimpleNamespace

import cv2
import numpy as np


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from screen import Screen  # noqa: E402
from cheats import Cheats  # noqa: E402


FOV = (300, 300)
CENTER = (FOV[0] // 2, FOV[1] // 2)


@dataclass
class Dummy:
    x: int
    y: int
    scale: float = 1.0
    lean: float = 0.0
    partial: bool = False

    @property
    def expected(self):
        head_w = max(4, int(16 * self.scale))
        head_h = max(4, int(18 * self.scale))
        body_h = max(12, int(42 * self.scale))
        head_y1 = int(self.y - body_h - head_h - int(4 * self.scale))
        return (
            self.x + int(self.lean * self.scale),
            head_y1 + head_h * 0.58,
        )


@dataclass
class Scene:
    name: str
    dummies: list
    expected_index: int
    distractors: tuple = ()


def hsv_to_bgr(h, s, v):
    pixel = np.array([[[h, s, v]]], dtype=np.uint8)
    return tuple(int(c) for c in cv2.cvtColor(pixel, cv2.COLOR_HSV2BGR)[0, 0])


def draw_dummy(img, dummy, color):
    x = int(dummy.x)
    y = int(dummy.y)
    scale = dummy.scale
    lean = int(dummy.lean * scale)
    head_w = max(4, int(16 * scale))
    head_h = max(4, int(18 * scale))
    shoulder_w = max(10, int(44 * scale))
    body_h = max(12, int(42 * scale))

    head_x1 = int(x - head_w // 2 + lean)
    head_y1 = int(y - body_h - head_h - int(4 * scale))
    head_x2 = head_x1 + head_w
    head_y2 = head_y1 + head_h

    if not dummy.partial:
        cv2.rectangle(img, (head_x1, head_y1), (head_x2, head_y2), color, -1)
        cv2.rectangle(
            img,
            (int(x - shoulder_w // 2), int(y - body_h)),
            (int(x + shoulder_w // 2), int(y - body_h + max(5, int(12 * scale)))),
            color,
            2,
        )
        cv2.line(
            img,
            (int(x - shoulder_w * 0.30), int(y - body_h + 4 * scale)),
            (int(x - shoulder_w * 0.42), int(y - body_h + body_h * 0.70)),
            color,
            max(1, int(3 * scale)),
        )
        cv2.line(
            img,
            (int(x + shoulder_w * 0.30), int(y - body_h + 4 * scale)),
            (int(x + shoulder_w * 0.42), int(y - body_h + body_h * 0.70)),
            color,
            max(1, int(3 * scale)),
        )
    else:
        cv2.rectangle(img, (head_x1, head_y1), (head_x2, head_y2), color, -1)
        cv2.line(
            img,
            (int(x - shoulder_w * 0.20), int(y - body_h + 6 * scale)),
            (int(x + shoulder_w * 0.12), int(y - body_h + 12 * scale)),
            color,
            max(1, int(3 * scale)),
        )


def make_scene_image(scene, hsv):
    img = np.zeros((FOV[1], FOV[0], 3), dtype=np.uint8)
    color = hsv_to_bgr(*hsv)
    for dummy in scene.dummies:
        draw_dummy(img, dummy, color)

    for rect, h, s, v in scene.distractors:
        x1, y1, x2, y2 = rect
        cv2.rectangle(img, (x1, y1), (x2, y2), hsv_to_bgr(h, s, v), -1)
    return img


def make_cfg(params):
    return SimpleNamespace(
        lower_color=np.array([params['lower_h'], params['lower_s'], params['lower_v']]),
        upper_color=np.array([params['upper_h'], 255, 255]),
        group_close_target_blobs_threshold=(2, 2),
        capture_fov_x=FOV[0],
        capture_fov_y=FOV[1],
        aim_fov_x=200,
        aim_fov_y=200,
        screen_center_offset=0,
        auto_detect_resolution=False,
        resolution_x=1920,
        resolution_y=1080,
        debug=False,
        display_mode='mask',
        trigger_threshold=8,
        aim_height=0.80,
        head_offset_near=params['near'],
        head_offset_mid=params['mid'],
        head_offset_far=params['far'],
        head_roi_ratio=params.get('head_roi_ratio', 0.30),
        target_lock_frames=12,
        target_switch_margin=params['switch_margin'],
        target_prediction=params.get('prediction', 0.36),
        aim_deadzone=params.get('aim_deadzone', 2),
        aim_smoothing_factor=params.get('aim_smoothing_factor', 0.24),
        aim_max_step=params.get('aim_max_step', 82),
        speed=params.get('speed', 1.68),
        y_speed_multiplier=1.0,
        recoil_mode='move',
        recoil_x=0.0,
        recoil_y=0.0,
        max_offset=100,
        recoil_recover=0.0,
        debug_refresh_interval=4,
    )


def make_screen(cfg, img):
    screen = Screen.__new__(Screen)
    screen.cfg = cfg
    screen.screen = (1920, 1080)
    screen.screen_center = (960, 540)
    screen.screen_region = (0, 0, 1920, 1080)
    screen.fov = FOV
    screen.fov_center = CENTER
    screen.fov_region = (810, 390, 1110, 690)
    screen.thresh = None
    screen.target = None
    screen.closest_contour = None
    screen.locked_target = None
    screen.locked_body = None
    screen.locked_body_center = None
    screen.locked_body_velocity = np.array((0.0, 0.0), dtype=float)
    screen.locked_head_window = None
    screen.stable_head_center = None
    screen.lock_misses = 0
    screen._fall_history = []
    screen.aim_was_active = False
    screen.filtered_target = None
    screen.previous_target = None
    screen.last_measurement = None
    screen.measurement_velocity = np.array((0.0, 0.0), dtype=float)
    screen.track_position = None
    screen.track_velocity = (0, 0)
    screen.track_acceleration = (0, 0)
    screen.debug_candidates = []
    screen.debug_frame = 0
    screen.img = None
    screen.aim_fov = (cfg.aim_fov_x, cfg.aim_fov_y)
    screen.screenshot = lambda region: img.copy()
    return screen


def make_motion_screen(cfg, image_holder):
    screen = make_screen(cfg, image_holder['img'])
    screen.screenshot = lambda region: image_holder['img'].copy()
    return screen


def evaluate(params, scenes):
    cfg = make_cfg(params)
    total = 0
    failures = []
    for scene in scenes:
        expected_dummy = scene.dummies[scene.expected_index]
        expected = expected_dummy.expected

        scene_errors = []
        for hsv in ((148, 235, 255), (151, 180, 210), (144, 145, 185), (156, 210, 230)):
            img = make_scene_image(scene, hsv)
            screen = make_screen(cfg, img)
            target, _ = screen.get_target(0, True)
            if target is None:
                scene_errors.append(200)
                continue

            predicted = (target[0] + CENTER[0], target[1] + CENTER[1])
            error = float(np.hypot(predicted[0] - expected[0], predicted[1] - expected[1]))
            scene_errors.append(error)

        scene_score = sum(scene_errors) / len(scene_errors)
        total += scene_score
        if scene_score > 9:
            failures.append((scene.name, round(scene_score, 2)))

    return total / len(scenes), failures


def evaluate_motion(params):
    cfg = make_cfg(params)
    frames = []
    for x in (118, 126, 135, 145, 156, 168, 181):
        frames.append(Scene('moving_lock', [Dummy(x, 196, 0.62), Dummy(198, 196, 0.62)], 0))

    holder = {'img': make_scene_image(frames[0], (148, 235, 255))}
    screen = make_motion_screen(cfg, holder)
    errors = []
    for scene in frames:
        holder['img'] = make_scene_image(scene, (148, 235, 255))
        target, _ = screen.get_target(0, True)
        expected = scene.dummies[scene.expected_index].expected
        if target is None:
            errors.append(200)
            continue
        predicted = (target[0] + CENTER[0], target[1] + CENTER[1])
        errors.append(float(np.hypot(predicted[0] - expected[0], predicted[1] - expected[1])))

    return sum(errors) / len(errors), max(errors)


def evaluate_jitter(params):
    cfg = make_cfg(params)
    holder = {'img': None}
    screen = make_motion_screen(cfg, holder)
    cheats = Cheats(cfg)
    rng = np.random.default_rng(7)
    targets = []
    moves = []

    for _ in range(80):
        jitter_x = int(rng.integers(-1, 2))
        jitter_y = int(rng.integers(-1, 2))
        scene = Scene('jitter_lock', [Dummy(150 + jitter_x, 196 + jitter_y, 0.72)], 0)
        holder['img'] = make_scene_image(scene, (148, 235, 255))
        target, _ = screen.get_target(0, True)
        if target is None:
            continue

        targets.append((target[0], target[1]))
        cheats.calculate_aim(True, target)
        moves.append((cheats.move_x, cheats.move_y))
        cheats.move_x, cheats.move_y = (0, 0)

    if not targets:
        return 999, 999, 999

    target_array = np.array(targets)
    move_array = np.array(moves) if moves else np.zeros((1, 2))
    target_jitter = float(np.mean(np.std(target_array, axis=0)))
    move_jitter = float(np.mean(np.std(move_array, axis=0)))
    move_energy = float(np.mean(np.linalg.norm(move_array, axis=1)))
    return target_jitter, move_jitter, move_energy


def build_scenes():
    return [
        Scene('near_center', [Dummy(150, 205, 1.25)], 0),
        Scene('mid_center', [Dummy(150, 196, 0.82)], 0),
        Scene('far_center', [Dummy(150, 184, 0.46)], 0),
        Scene('far_lean', [Dummy(154, 184, 0.45, lean=3.0)], 0),
        Scene('partial_head', [Dummy(148, 184, 0.50, partial=True)], 0),
        Scene(
            'three_dummies_left_closest',
            [Dummy(104, 196, 0.62), Dummy(143, 196, 0.62), Dummy(182, 196, 0.62)],
            1,
        ),
        Scene(
            'three_dummies_right_closest',
            [Dummy(117, 196, 0.62), Dummy(156, 196, 0.62), Dummy(195, 196, 0.62)],
            1,
        ),
        Scene(
            'crowded_close',
            [Dummy(132, 197, 0.72), Dummy(157, 197, 0.72), Dummy(184, 197, 0.72)],
            1,
        ),
        Scene(
            'purple_map_noise',
            [Dummy(151, 196, 0.70)],
            0,
            distractors=(((28, 30, 116, 36), 150, 130, 180), ((216, 116, 260, 123), 148, 125, 170)),
        ),
    ]


def main():
    scenes = build_scenes()
    best = None
    show_details = '--details' in sys.argv
    full_grid = '--full' in sys.argv or os.environ.get('VISION_TUNE_FULL') == '1'
    if full_grid:
        grid = itertools.product(
            (132, 135, 138),
            (162, 165, 168),
            (105, 115, 130),
            (135, 150, 165),
            (0.16, 0.18, 0.20),
            (0.20, 0.22, 0.24),
            (0.14, 0.17, 0.20, 0.23, 0.25),
            (0.65, 0.70, 0.78),
        )
    else:
        # Fast smoke grid centered around the current project defaults. The
        # full grid is useful for offline tuning, but it is too slow for every
        # regression pass.
        grid = itertools.product(
            (132, 135),
            (162,),
            (105, 115),
            (135, 150),
            (0.13, 0.16),
            (0.15, 0.18),
            (0.18, 0.20),
            (0.60, 0.65),
        )

    for lower_h, upper_h, lower_s, lower_v, near, mid, far, switch_margin in grid:
        params = {
            'lower_h': lower_h,
            'upper_h': upper_h,
            'lower_s': lower_s,
            'lower_v': lower_v,
            'near': near,
            'mid': mid,
            'far': far,
            'switch_margin': switch_margin,
        }
        score, failures = evaluate(params, scenes)
        if best is None or score < best[0]:
            best = (score, params, failures)

    score, params, failures = best
    print(f'best_score={score:.3f}')
    for key in sorted(params):
        print(f'{key}={params[key]}')
    if failures:
        print('failures=' + ', '.join(f'{name}:{value}' for name, value in failures))
    else:
        print('failures=none')
    motion_avg, motion_max = evaluate_motion(params)
    print(f'motion_avg={motion_avg:.3f}')
    print(f'motion_max={motion_max:.3f}')
    target_jitter, move_jitter, move_energy = evaluate_jitter(params)
    print(f'jitter_target={target_jitter:.3f}')
    print(f'jitter_move={move_jitter:.3f}')
    print(f'jitter_move_energy={move_energy:.3f}')

    if show_details:
        cfg = make_cfg(params)
        for scene in scenes:
            expected = scene.dummies[scene.expected_index].expected
            img = make_scene_image(scene, (148, 235, 255))
            screen = make_screen(cfg, img)
            target, _ = screen.get_target(0, True)
            if target is None:
                print(f'{scene.name}: target=None expected={expected}')
                continue
            predicted = (target[0] + CENTER[0], target[1] + CENTER[1])
            error = float(np.hypot(predicted[0] - expected[0], predicted[1] - expected[1]))
            print(f'{scene.name}: predicted=({predicted[0]:.1f},{predicted[1]:.1f}) expected=({expected[0]:.1f},{expected[1]:.1f}) error={error:.2f}')


if __name__ == '__main__':
    main()
