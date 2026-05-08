import os
import sys
from types import SimpleNamespace

import numpy as np

ROOT = os.path.dirname(os.path.dirname(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from aim_output import AimOutput
from cheats import Cheats


class VirtualMouse:
    def __init__(self):
        self.position = np.array((0.0, 0.0), dtype=float)
        self.moves = []

    def move(self, x, y):
        move = np.array((float(x), float(y)), dtype=float)
        self.position += move
        self.moves.append(move)


def make_cfg():
    return SimpleNamespace(
        aim_deadzone=2,
        speed=1.68,
        y_speed_multiplier=1.0,
        aim_smoothing_factor=0.808,
        aim_max_step=82,
        aim_output_blend_ticks=2,
        aim_output_hz=240,
        recoil_mode='move'
    )


def simulate(targets, ticks_per_frame=1):
    cfg = make_cfg()
    mouse = VirtualMouse()
    cheats = Cheats(cfg)
    output = AimOutput(cfg, mouse)
    errors = []
    frame_moves = []

    for target in targets:
        target = np.array(target, dtype=float)
        before = mouse.position.copy()
        error = target - mouse.position
        cheats.calculate_aim(True, (float(error[0]), float(error[1])))
        output.set_move(cheats.move_x, cheats.move_y)

        for _ in range(ticks_per_frame):
            move_x, move_y = output.take_next_move()
            if move_x != 0 or move_y != 0:
                mouse.move(move_x, move_y)

        errors.append(target - mouse.position)
        frame_moves.append(mouse.position - before)

    return np.array(errors), np.array(frame_moves), np.array(mouse.moves)


def settle_target(target, frames=80):
    return [target for _ in range(frames)]


def test_static_target_converges_without_chatter():
    errors, frame_moves, _ = simulate(settle_target((80, -42), 90))
    final_error = np.linalg.norm(errors[-1])
    tail_move = np.max(np.linalg.norm(frame_moves[-20:], axis=1))
    tail_error = np.max(np.linalg.norm(errors[-20:], axis=1))

    assert final_error <= 3.2, f'static target did not converge: final error {final_error:.3f}'
    assert tail_move <= 1.2, f'lock tail still moves too much: {tail_move:.3f}'
    assert tail_error <= 4.5, f'lock tail error too large: {tail_error:.3f}'
    return {
        'final_error': final_error,
        'tail_max_move': tail_move,
        'tail_max_error': tail_error
    }


def test_no_overshoot_on_fast_acquire():
    errors, frame_moves, _ = simulate(settle_target((120, 0), 70))
    x_errors = errors[:, 0]
    sign_changes = np.count_nonzero(np.diff(np.signbit(x_errors)))
    assert sign_changes <= 1, f'acquire overshot repeatedly: {sign_changes} sign changes'
    assert abs(x_errors[-1]) <= 3.0, f'acquire final x error too high: {x_errors[-1]:.3f}'
    return {
        'x_final_error': abs(x_errors[-1]),
        'x_sign_changes': sign_changes,
        'peak_frame_move': np.max(np.linalg.norm(frame_moves, axis=1))
    }


def test_measurement_noise_does_not_create_jitter():
    rng = np.random.default_rng(7)
    targets = [(60, -26)] * 45
    targets += [(60 + rng.uniform(-1.1, 1.1), -26 + rng.uniform(-1.1, 1.1)) for _ in range(80)]
    errors, frame_moves, _ = simulate(targets)
    tail_move = np.percentile(np.linalg.norm(frame_moves[-50:], axis=1), 95)
    assert tail_move <= 1.35, f'noisy lock jitter too high: {tail_move:.3f}'
    return {
        'noise_95p_move': tail_move,
        'noise_95p_error': np.percentile(np.linalg.norm(errors[-50:], axis=1), 95)
    }


def test_linear_moving_target_tracks_tightly():
    targets = []
    for tick in range(110):
        targets.append((-55 + tick * 0.78, -24 + np.sin(tick / 9) * 1.4))

    errors, _, _ = simulate(targets)
    tail_error = np.percentile(np.linalg.norm(errors[-40:], axis=1), 90)
    assert tail_error <= 9.0, f'moving target tracking error too high: {tail_error:.3f}'
    return {
        'moving_90p_error': tail_error,
        'moving_final_error': np.linalg.norm(errors[-1])
    }


def test_reverse_direction_does_not_bounce():
    targets = []
    for tick in range(55):
        targets.append((-40 + tick * 0.92, -20))
    for tick in range(55):
        targets.append((10 - tick * 0.92, -20))

    errors, frame_moves, _ = simulate(targets)
    reversal_moves = frame_moves[53:64, 0]
    sign_changes = np.count_nonzero(np.diff(np.signbit(reversal_moves)))
    assert sign_changes <= 2, f'reversal bounced too much: {sign_changes} sign changes'
    tail_error = np.percentile(np.linalg.norm(errors[-25:], axis=1), 90)
    assert tail_error <= 10.0, 'reverse tracking ended too far from target'
    return {
        'reversal_sign_changes': sign_changes,
        'reverse_tail_90p_error': tail_error
    }


def test_manual_nudge_recovers_without_chatter():
    targets = [(0, 0)] * 12 + [(7, -4)] * 38 + [(7.8, -3.4), (6.9, -4.5)] * 18
    errors, frame_moves, _ = simulate(targets)
    tail_move = np.percentile(np.linalg.norm(frame_moves[-20:], axis=1), 95)
    assert np.linalg.norm(errors[-1]) <= 4.0, f'manual nudge did not recover: {np.linalg.norm(errors[-1]):.3f}'
    assert tail_move <= 1.5, f'manual nudge caused chatter: {tail_move:.3f}'
    return {
        'nudge_final_error': np.linalg.norm(errors[-1]),
        'nudge_95p_tail_move': tail_move
    }


def test_two_tick_output_cadence_matches_one_tick():
    one_errors, one_moves, _ = simulate(settle_target((80, -42), 90), ticks_per_frame=1)
    two_errors, two_moves, _ = simulate(settle_target((80, -42), 90), ticks_per_frame=2)
    one_final = np.linalg.norm(one_errors[-1])
    two_final = np.linalg.norm(two_errors[-1])
    one_tail = np.max(np.linalg.norm(one_moves[-20:], axis=1))
    two_tail = np.max(np.linalg.norm(two_moves[-20:], axis=1))

    assert max(one_final, two_final) <= 3.2, f'cadence mismatch leaves target too far: one={one_final:.3f}, two={two_final:.3f}'
    assert max(one_tail, two_tail) <= 1.2, f'cadence mismatch causes tail movement: one={one_tail:.3f}, two={two_tail:.3f}'
    return {
        'one_tick_final': one_final,
        'two_tick_final': two_final,
        'one_tick_tail': one_tail,
        'two_tick_tail': two_tail
    }


def test_one_tick_output_cadence_tracks_motion():
    targets = [(-55 + tick * 0.78, -24 + np.sin(tick / 9) * 1.4) for tick in range(110)]
    errors, _, _ = simulate(targets, ticks_per_frame=1)
    tail_error = np.percentile(np.linalg.norm(errors[-40:], axis=1), 90)
    assert tail_error <= 9.0, f'1-tick moving target tracking error too high: {tail_error:.3f}'
    return {
        'one_tick_moving_90p_error': tail_error,
        'one_tick_moving_final_error': np.linalg.norm(errors[-1])
    }


def main():
    tests = [
        test_static_target_converges_without_chatter,
        test_no_overshoot_on_fast_acquire,
        test_measurement_noise_does_not_create_jitter,
        test_linear_moving_target_tracks_tightly,
        test_reverse_direction_does_not_bounce,
        test_manual_nudge_recovers_without_chatter,
        test_two_tick_output_cadence_matches_one_tick,
        test_one_tick_output_cadence_tracks_motion,
    ]
    for test in tests:
        metrics = test()
        formatted = ', '.join(f'{key}={value:.3f}' for key, value in metrics.items())
        print(f'{test.__name__}: ok ({formatted})')
    print('movement stress lab: ok')


if __name__ == '__main__':
    main()
