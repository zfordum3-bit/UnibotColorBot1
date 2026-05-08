import threading
import time


class AimOutput:
    RESIDUAL_KEEP = 0.35
    RESIDUAL_CAP = 1.25

    def __init__(self, config, mouse):
        self.cfg = config
        self.mouse = mouse
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.pending_x = 0.0
        self.pending_y = 0.0
        self.ticks_remaining = 0

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=0.5)

    def set_move(self, x, y):
        with self.lock:
            if x == 0 and y == 0:
                self.pending_x = 0.0
                self.pending_y = 0.0
                self.ticks_remaining = 0
            else:
                next_x = float(x)
                next_y = float(y)
                if self.ticks_remaining > 0:
                    if self.same_direction(next_x, self.pending_x):
                        next_x += self.pending_x * self.RESIDUAL_KEEP
                    if self.same_direction(next_y, self.pending_y):
                        next_y += self.pending_y * self.RESIDUAL_KEEP

                next_x = self.cap_residual(next_x, x)
                next_y = self.cap_residual(next_y, y)
                self.pending_x = next_x
                self.pending_y = next_y
                self.ticks_remaining = max(self.ticks_remaining, max(self.cfg.aim_output_blend_ticks, 1))

    def run(self):
        interval = 1 / max(self.cfg.aim_output_hz, 1)
        next_time = time.perf_counter()

        while not self.stop_event.is_set():
            move_x, move_y = self.take_next_move()
            if move_x != 0 or move_y != 0:
                self.mouse.move(move_x, move_y)

            next_time += interval
            sleep_time = next_time - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_time = time.perf_counter()

    def take_next_move(self):
        with self.lock:
            if self.ticks_remaining <= 0:
                return 0.0, 0.0

            move_x = self.pending_x / self.ticks_remaining
            move_y = self.pending_y / self.ticks_remaining
            self.pending_x -= move_x
            self.pending_y -= move_y
            self.ticks_remaining -= 1

            if self.ticks_remaining <= 0:
                self.pending_x = 0.0
                self.pending_y = 0.0

            return move_x, move_y

    @staticmethod
    def same_direction(a, b):
        return a == 0 or b == 0 or (a > 0) == (b > 0)

    @classmethod
    def cap_residual(cls, value, requested):
        limit = max(abs(float(requested)) * cls.RESIDUAL_CAP, 1.0)
        if value > limit:
            return limit
        if value < -limit:
            return -limit
        return value
