import os
import sys
from types import SimpleNamespace

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from cheats import Cheats
from aim_output import AimOutput
from screen import Screen


def make_screen():
    screen = object.__new__(Screen)
    screen.cfg = SimpleNamespace(
        head_offset_near=0.13,
        head_offset_mid=0.15,
        head_offset_far=0.18,
        head_roi_ratio=0.30,
        target_prediction=0.36,
        aim_deadzone=2
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
    screen._fall_history = []
    screen.filtered_target = None
    screen.previous_target = None
    screen.track_position = None
    screen.track_velocity = (0, 0)
    screen.track_acceleration = (0, 0)
    screen.last_measurement = None
    screen.measurement_velocity = np.array((0.0, 0.0), dtype=float)
    return screen


def test_sticky_lock():
    screen = make_screen()
    locked = {
        'body_rect': (100, 80, 130, 160),
        'body_center': (115, 120),
        'center': (115, 92),
        'target': (-35, -58),
        'score': 80,
        'head_window': (106, 86, 124, 100)
    }
    closer_new_target = {
        'body_rect': (170, 80, 200, 160),
        'body_center': (185, 120),
        'center': (185, 92),
        'target': (35, -58),
        'score': 1,
        'head_window': (176, 86, 194, 100)
    }
    screen.locked_target = locked
    screen.locked_body = locked['body_rect']
    screen.locked_head_window = locked['head_window']

    chosen = screen.choose_body_candidate([closer_new_target, locked], aim_active=True, pressed_this_frame=False)
    assert chosen is locked, 'sticky lock switched to another target'


def test_body_tracker_prefers_predicted_locked_entity():
    screen = make_screen()
    locked = {
        'body_rect': (100, 80, 130, 160),
        'body_center': (115, 120),
        'center': (115, 92),
        'target': (-35, -58),
        'score': 80,
        'confidence': 0.9,
        'head_window': (106, 86, 124, 100)
    }
    moved_locked = {
        'body_rect': (110, 80, 140, 160),
        'body_center': (125, 120),
        'center': (125, 92),
        'target': (-25, -58),
        'score': 60,
        'confidence': 0.9,
        'head_window': (116, 86, 134, 100)
    }
    distractor = {
        'body_rect': (155, 80, 185, 160),
        'body_center': (170, 120),
        'center': (170, 92),
        'target': (20, -58),
        'score': 1,
        'confidence': 0.9,
        'head_window': (161, 86, 179, 100)
    }
    screen.locked_target = locked
    screen.locked_body = locked['body_rect']
    screen.locked_body_center = np.array(locked['body_center'], dtype=float)
    screen.locked_body_velocity = np.array((10.0, 0.0), dtype=float)
    screen.locked_head_window = locked['head_window']
    chosen = screen.choose_body_candidate([distractor, moved_locked], aim_active=True, pressed_this_frame=False)
    assert chosen is moved_locked, 'body tracker did not keep the predicted locked entity'


def test_far_head_model_stays_top():
    screen = make_screen()
    mask = np.zeros((300, 300), dtype=np.uint8)
    body = (120, 88, 148, 128)
    cv2.rectangle(mask, (120, 88), (148, 128), 255, -1)
    candidate = screen.make_head_model_candidate(body, mask)
    assert candidate is not None, 'far head model produced no candidate'
    head_y = candidate['center'][1]
    assert head_y <= body[1] + (body[3] - body[1]) * 0.35, 'far head model fell too low'


def test_distant_full_body_is_not_exposed_fragment():
    screen = make_screen()
    body = (120, 90, 138, 114)
    assert not screen.is_exposed_fragment(body), 'distant full body was treated as exposed center blob'
    head_roi = screen.get_head_roi(body)
    assert head_roi[3] <= body[1] + 14, 'small body head roi included too much body'


def make_humanoid_mask():
    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.rectangle(mask, (136, 88), (144, 99), 255, 1)
    cv2.line(mask, (132, 104), (148, 104), 255, 2)
    cv2.line(mask, (132, 104), (124, 124), 255, 2)
    cv2.line(mask, (148, 104), (156, 124), 255, 2)
    cv2.rectangle(mask, (132, 106), (148, 136), 255, 1)
    cv2.line(mask, (136, 136), (130, 160), 255, 2)
    cv2.line(mask, (144, 136), (150, 160), 255, 2)
    return mask


def test_body_model_confidence_prefers_humanoid_over_noise():
    screen = make_screen()
    humanoid_mask = make_humanoid_mask()
    humanoid_rect = (122, 86, 158, 162)
    humanoid_score = screen.body_model_confidence(humanoid_rect, humanoid_mask)

    noise_mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.circle(noise_mask, (140, 124), 24, 255, -1)
    noise_rect = (116, 100, 164, 148)
    noise_score = screen.body_model_confidence(noise_rect, noise_mask)

    assert humanoid_score >= 0.12, 'humanoid model confidence was too low'
    assert noise_score < humanoid_score - 0.08, 'noise model scored too close to humanoid'


def test_make_body_candidates_filters_skill_blob_noise():
    screen = make_screen()
    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.circle(mask, (140, 124), 24, 255, -1)
    rect = (116, 100, 164, 148)
    candidates = screen.make_body_candidates(rect, [], mask)
    assert candidates == [], 'skill-like blob produced aim candidates'


def test_low_quality_purple_square_cannot_start_lock():
    screen = make_screen()
    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.rectangle(mask, (135, 135), (146, 146), 255, -1)
    rect = (135, 135, 147, 147)
    candidates = screen.make_body_candidates(rect, [], mask)
    assert candidates == [], 'low-quality purple square produced aim candidates'


def test_isolated_purple_dot_cannot_start_lock():
    screen = make_screen()
    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.circle(mask, (150, 150), 3, 255, -1)
    rect = (147, 147, 154, 154)
    candidates = screen.make_body_candidates(rect, [], mask)
    assert candidates == [], 'isolated purple dot produced aim candidates'


def test_locked_near_fragment_can_continue_tracking():
    screen = make_screen()
    screen.locked_body = (146, 146, 156, 156)
    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.circle(mask, (151, 151), 3, 255, -1)
    rect = (148, 148, 155, 155)
    candidates = screen.make_body_candidates(rect, [], mask)
    assert candidates != [], 'near locked fragment was rejected'


def test_prediction_leads_horizontal_motion():
    screen = make_screen()
    outputs = []
    for x in [-42, -36, -30, -24, -18, -12]:
        outputs.append(screen.smooth_target((x, -20)))
    assert outputs[-1][0] > -12, 'prediction did not lead horizontal motion'


def test_prediction_keeps_up_with_irregular_motion():
    screen = make_screen()
    measurements = [(-42, -22), (-35, -22), (-29, -21), (-19, -23), (-11, -22), (-4, -22)]
    output = measurements[0]
    for point in measurements:
        output = screen.smooth_target(point)
    assert output[0] >= measurements[-1][0] - 1.0, 'prediction lagged irregular horizontal motion'


def test_close_controller_does_not_overshoot():
    cfg = SimpleNamespace(
        aim_deadzone=2,
        speed=1.68,
        y_speed_multiplier=1.0,
        aim_smoothing_factor=0.808,
        aim_max_step=82,
        recoil_mode='move'
    )
    cheats = Cheats(cfg)
    cheats.calculate_aim(True, (6, 0))
    assert abs(cheats.move_x) <= 6, 'close controller overstepped target error'


def test_lock_does_not_chatter_on_micro_error():
    cfg = SimpleNamespace(
        aim_deadzone=2,
        speed=1.68,
        y_speed_multiplier=1.0,
        aim_smoothing_factor=0.808,
        aim_max_step=82,
        recoil_mode='move'
    )
    cheats = Cheats(cfg)
    for error in [(3, 1), (-3, 1), (2, -2), (-2, 2)]:
        cheats.calculate_aim(True, error)
        assert abs(cheats.move_x) <= 1.9, 'micro error generated too much x output'
        assert abs(cheats.move_y) <= 1.9, 'micro error generated too much y output'


def test_controller_tracks_moving_target_in_lock_state():
    cfg = SimpleNamespace(
        aim_deadzone=2,
        speed=1.68,
        y_speed_multiplier=1.0,
        aim_smoothing_factor=0.808,
        aim_max_step=82,
        recoil_mode='move'
    )
    cheats = Cheats(cfg)
    for error in [(1, 0), (1, 0)]:
        cheats.calculate_aim(True, error)
    cheats.calculate_aim(True, (5, 0))
    assert cheats.move_x > 0, 'lock state ignored real target movement'


def test_stable_head_rejects_single_frame_jump():
    screen = make_screen()
    screen.locked_head_window = (92, 82, 132, 104)
    screen.stable_head_center = np.array((112.0, 92.0), dtype=float)
    noisy_candidate = {
        'rect': (124, 96, 132, 104),
        'body_rect': (92, 80, 132, 160),
        'center': (132.0, 104.0),
        'target': (-18.0, -46.0),
        'source': 'contour',
        'confidence': 0.50
    }
    target = screen.stabilize_candidate_target(noisy_candidate)
    center = np.array((target[0] + screen.fov_center[0], target[1] + screen.fov_center[1]))
    assert np.linalg.norm(center - np.array((112.0, 92.0))) <= 10.0, 'single-frame head jump moved stable target too far'


def test_output_residual_does_not_push_against_reversal():
    cfg = SimpleNamespace(aim_output_blend_ticks=2, aim_output_hz=240)
    mouse = SimpleNamespace(move=lambda x, y: None)
    output = AimOutput(cfg, mouse)
    output.set_move(10, 0)
    first = output.take_next_move()
    output.set_move(-4, 0)
    second = output.take_next_move()
    assert first[0] > 0, 'initial output did not move right'
    assert second[0] < 0, 'opposite correction was held back by stale residual'


def test_output_residual_is_capped():
    cfg = SimpleNamespace(aim_output_blend_ticks=4, aim_output_hz=240)
    mouse = SimpleNamespace(move=lambda x, y: None)
    output = AimOutput(cfg, mouse)
    for _ in range(5):
        output.set_move(2, 0)
    assert abs(output.pending_x) <= 2.5, 'output residual accumulated too much movement'


def main():
    test_sticky_lock()
    test_body_tracker_prefers_predicted_locked_entity()
    test_far_head_model_stays_top()
    test_distant_full_body_is_not_exposed_fragment()
    test_body_model_confidence_prefers_humanoid_over_noise()
    test_make_body_candidates_filters_skill_blob_noise()
    test_low_quality_purple_square_cannot_start_lock()
    test_isolated_purple_dot_cannot_start_lock()
    test_locked_near_fragment_can_continue_tracking()
    test_prediction_leads_horizontal_motion()
    test_prediction_keeps_up_with_irregular_motion()
    test_close_controller_does_not_overshoot()
    test_lock_does_not_chatter_on_micro_error()
    test_controller_tracks_moving_target_in_lock_state()
    test_stable_head_rejects_single_frame_jump()
    test_output_residual_does_not_push_against_reversal()
    test_output_residual_is_capped()
    print('final aim simulation: ok')


if __name__ == '__main__':
    main()
