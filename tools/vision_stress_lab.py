import os
import sys
from types import SimpleNamespace

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from screen import Screen


def make_screen():
    screen = object.__new__(Screen)
    screen.cfg = SimpleNamespace(
        group_close_target_blobs_threshold=(2, 2),
        head_offset_near=0.13,
        head_offset_mid=0.15,
        head_offset_far=0.18,
        head_roi_ratio=0.30,
        target_prediction=0.36,
        target_lock_frames=12,
        aim_deadzone=2,
        debug_refresh_interval=4
    )
    screen.fov_center = (150, 150)
    screen.fov = (300, 300)
    screen.locked_target = None
    screen.locked_body = None
    screen.locked_body_center = None
    screen.locked_body_velocity = np.array((0.0, 0.0), dtype=float)
    screen.locked_head_window = None
    screen.stable_head_center = None
    screen.lock_misses = 0
    screen.filtered_target = None
    screen.previous_target = None
    screen.track_position = None
    screen.track_velocity = (0, 0)
    screen.track_acceleration = (0, 0)
    screen.last_measurement = None
    screen.measurement_velocity = np.array((0.0, 0.0), dtype=float)
    screen._fall_history = []
    return screen


def draw_humanoid(mask, cx, top, scale=1.0):
    head_w = max(5, int(9 * scale))
    head_h = max(7, int(12 * scale))
    shoulder = max(14, int(30 * scale))
    torso_w = max(12, int(18 * scale))
    torso_h = max(24, int(34 * scale))
    leg_h = max(18, int(28 * scale))
    arm_h = max(14, int(22 * scale))

    head_x1 = int(cx - head_w / 2)
    head_y1 = int(top)
    head_x2 = int(cx + head_w / 2)
    head_y2 = int(top + head_h)
    cv2.rectangle(mask, (head_x1, head_y1), (head_x2, head_y2), 255, 1)

    neck_y = head_y2 + max(2, int(3 * scale))
    cv2.line(mask, (int(cx - shoulder / 2), neck_y), (int(cx + shoulder / 2), neck_y), 255, max(1, int(2 * scale)))
    cv2.line(mask, (int(cx - shoulder / 2), neck_y), (int(cx - shoulder * 0.78), neck_y + arm_h), 255, max(1, int(2 * scale)))
    cv2.line(mask, (int(cx + shoulder / 2), neck_y), (int(cx + shoulder * 0.78), neck_y + arm_h), 255, max(1, int(2 * scale)))
    cv2.rectangle(mask, (int(cx - torso_w / 2), neck_y + 2), (int(cx + torso_w / 2), neck_y + torso_h), 255, 1)
    hip_y = neck_y + torso_h
    cv2.line(mask, (int(cx - torso_w * 0.25), hip_y), (int(cx - torso_w * 0.65), hip_y + leg_h), 255, max(1, int(2 * scale)))
    cv2.line(mask, (int(cx + torso_w * 0.25), hip_y), (int(cx + torso_w * 0.65), hip_y + leg_h), 255, max(1, int(2 * scale)))
    return (int(cx - shoulder), int(top), int(cx + shoulder), int(hip_y + leg_h))


def collect_candidates(screen, mask):
    clean_kernel = np.ones((3, 3), np.uint8)
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, clean_kernel, iterations=1)
    kernel = np.ones(screen.cfg.group_close_target_blobs_threshold, np.uint8)
    thresh = cv2.dilate(closed, kernel, iterations=2)
    raw_contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

    target_groups = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h < 4:
            continue
        rect = (x, y, x + w, y + h)
        merged = False
        for index, group in enumerate(target_groups):
            if screen.rect_distance(rect, group) <= screen.group_distance(rect, group):
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

    candidates = []
    for group in target_groups:
        candidates.extend(screen.make_body_candidates(group, raw_contours, closed))
    return candidates


def choose(screen, candidates):
    if not candidates:
        return None
    return screen.choose_body_candidate(candidates, aim_active=True, pressed_this_frame=True)


def assert_head_like(candidate, expected_x, expected_y, tolerance):
    assert candidate is not None, 'no candidate selected'
    cx, cy = candidate['center']
    distance = float(np.hypot(cx - expected_x, cy - expected_y))
    assert distance <= tolerance, f'candidate center {candidate["center"]} too far from expected {(expected_x, expected_y)}'


def scenario_single_humanoid():
    screen = make_screen()
    mask = np.zeros((300, 300), dtype=np.uint8)
    draw_humanoid(mask, 150, 86, 1.0)
    candidate = choose(screen, collect_candidates(screen, mask))
    assert_head_like(candidate, 150, 94, 16)


def scenario_humanoid_beats_dot_noise():
    screen = make_screen()
    mask = np.zeros((300, 300), dtype=np.uint8)
    draw_humanoid(mask, 124, 90, 0.95)
    cv2.circle(mask, (150, 150), 3, 255, -1)
    candidate = choose(screen, collect_candidates(screen, mask))
    assert candidate is not None, 'humanoid was lost with dot noise'
    assert candidate.get('source') != 'exposed' or candidate.get('model_confidence', 0) >= 0.30, 'dot noise won target selection'
    assert candidate['center'][1] < 120, f'candidate was not on upper body/head: {candidate}'


def scenario_skill_blob_rejected():
    screen = make_screen()
    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.circle(mask, (150, 150), 24, 255, -1)
    candidates = collect_candidates(screen, mask)
    assert candidates == [], 'skill blob produced candidates'


def scenario_map_color_blocks_rejected():
    screen = make_screen()
    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.rectangle(mask, (118, 122), (178, 154), 255, -1)
    cv2.rectangle(mask, (205, 74), (254, 88), 255, -1)
    candidates = collect_candidates(screen, mask)
    assert candidates == [], f'map color noise produced candidates: {candidates}'


def scenario_fallen_body_rejected_as_new_target():
    screen = make_screen()
    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.line(mask, (86, 178), (176, 178), 255, 2)
    cv2.rectangle(mask, (102, 166), (128, 184), 255, 1)
    cv2.line(mask, (132, 176), (176, 190), 255, 2)
    candidates = collect_candidates(screen, mask)
    assert candidates == [], f'fallen body produced candidates: {candidates}'


def scenario_multi_target_closest_body():
    screen = make_screen()
    mask = np.zeros((300, 300), dtype=np.uint8)
    draw_humanoid(mask, 112, 92, 0.85)
    draw_humanoid(mask, 190, 88, 1.0)
    candidate = choose(screen, collect_candidates(screen, mask))
    assert candidate is not None, 'multi target produced no candidate'
    assert candidate['body_center'][0] < 155, f'wrong target selected: {candidate}'


def scenario_merged_close_targets_split_back_to_bodies():
    screen = make_screen()
    mask = np.zeros((300, 300), dtype=np.uint8)
    draw_humanoid(mask, 104, 157, 0.62)
    draw_humanoid(mask, 143, 157, 0.62)
    draw_humanoid(mask, 182, 157, 0.62)

    raw_contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    merged_rect = (90, 157, 199, 191)
    candidate = choose(screen, screen.make_body_candidates(merged_rect, raw_contours, mask))
    assert candidate is not None, 'merged close targets produced no candidate'
    assert abs(candidate['center'][0] - 143) <= 3, f'merged targets were not split to closest head: {candidate}'
    assert candidate['center'][1] <= candidate['head_window'][3], f'merged targets selected below head window: {candidate}'


def scenario_sticky_lock_projects_through_merged_neighbor():
    screen = make_screen()
    screen.locked_body = (104, 157, 135, 191)
    screen.locked_body_center = np.array((119.5, 174.0), dtype=float)
    screen.locked_body_velocity = np.array((9.0, 0.0), dtype=float)
    screen.locked_target = {'center': (119.0, 163.0)}

    mask = np.zeros((300, 300), dtype=np.uint8)
    draw_humanoid(mask, 156, 157, 0.62)
    draw_humanoid(mask, 198, 157, 0.62)
    cv2.line(mask, (170, 163), (184, 163), 255, 2)
    raw_contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    merged_rect = (142, 157, 215, 191)

    candidate = choose(screen, screen.make_body_candidates(merged_rect, raw_contours, mask))
    assert candidate is not None, 'sticky projection produced no candidate in merged neighbor case'
    assert candidate['center'][0] < 180, f'sticky lock jumped to neighbor: {candidate}'
    assert candidate['center'][1] <= candidate['head_window'][3], f'sticky lock selected below head window: {candidate}'


def scenario_partial_exposure_allowed_when_not_dot():
    screen = make_screen()
    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.rectangle(mask, (138, 118), (154, 140), 255, 1)
    cv2.line(mask, (138, 120), (128, 136), 255, 2)
    candidates = collect_candidates(screen, mask)
    assert candidates != [], 'larger partial exposure was rejected'


def scenario_low_quality_square_rejected():
    screen = make_screen()
    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.rectangle(mask, (142, 142), (154, 154), 255, -1)
    candidates = collect_candidates(screen, mask)
    assert candidates == [], 'low quality square produced candidates'


def main():
    scenarios = [
        scenario_single_humanoid,
        scenario_humanoid_beats_dot_noise,
        scenario_skill_blob_rejected,
        scenario_map_color_blocks_rejected,
        scenario_fallen_body_rejected_as_new_target,
        scenario_multi_target_closest_body,
        scenario_merged_close_targets_split_back_to_bodies,
        scenario_sticky_lock_projects_through_merged_neighbor,
        scenario_partial_exposure_allowed_when_not_dot,
        scenario_low_quality_square_rejected,
    ]

    for scenario in scenarios:
        scenario()
        print(f'{scenario.__name__}: ok')
    print('vision stress lab: ok')


if __name__ == '__main__':
    main()
