"""
    Unibot - MAKCU serial mouse backend.
"""
from .base_microcontroller_mouse import BaseMicrocontrollerMouse
import serial
import time


class MicrocontrollerSerialMouse(BaseMicrocontrollerMouse):
    MAKCU_BAUD_RATES = (4000000, 115200)

    def __init__(self, config):
        super().__init__(config)
        self.board = None
        self.baud_rate = None
        self.connect_to_board()


    def connect_to_board(self):
        port = f'COM{self.cfg.com_port}'
        last_error = None
        fallback_baud_rate = None

        for baud_rate in self.MAKCU_BAUD_RATES:
            try:
                board = serial.Serial(port, baud_rate, timeout=0.05, write_timeout=0.05)
                time.sleep(0.2)
                board.reset_input_buffer()
                board.write(b'km.version()\r\n')
                board.flush()
                response = self.read_available(board, timeout=0.25)

                if response:
                    self.board = board
                    self.baud_rate = baud_rate
                    print(f'Serial connected to MAKCU on {port} @ {baud_rate}: {response}')
                    return

                fallback_baud_rate = fallback_baud_rate or baud_rate
                board.close()
            except Exception as e:
                last_error = e
                try:
                    board.close()
                except Exception:
                    pass

        if fallback_baud_rate is not None:
            self.board = serial.Serial(port, fallback_baud_rate, timeout=0.05, write_timeout=0.05)
            self.baud_rate = fallback_baud_rate
            print(f'Serial connected to MAKCU on {port} @ {fallback_baud_rate} (no handshake response)')
            return

        print(f'ERROR: Could not connect to MAKCU on {port}. {last_error}')
        raise ConnectionError()


    @staticmethod
    def read_available(board, timeout=0.05):
        end_time = time.time() + timeout
        chunks = []

        while time.time() < end_time:
            waiting = board.in_waiting
            if waiting:
                chunks.append(board.read(waiting))
                end_time = time.time() + 0.02
            else:
                time.sleep(0.005)

        if not chunks:
            return ''

        return b''.join(chunks).decode('utf-8', errors='replace').strip()


    @staticmethod
    def get_move_cmd(x, y):
        return f'km.move({int(x)},{int(y)})\r\n'


    def send_command(self, command: str, expect_response=False):
        with self.send_command_lock:
            try:
                self.board.write(command.encode('ascii'))
                self.board.flush()

                if expect_response:
                    response = self.get_response()
                    print(f'(Serial) Sent: {command.strip()} | Response: {response or "no response"}')
            except Exception as e:
                print(f'(Serial) Send error: {e}')


    def get_response(self):
        try:
            return self.read_available(self.board, timeout=0.05)
        except Exception:
            return ''


    def send_move(self, x: int, y: int):
        if x == 0 and y == 0:
            return

        self.send_command(self.get_move_cmd(x, y))


    def send_click(self, delay_before_click: int = 0):
        time.sleep(delay_before_click)
        self.last_click_time = time.time()
        self.send_command('km.click(1)\r\n')


    def close_connection(self):
        if self.board is not None:
            try:
                self.board.close()
            except Exception:
                pass
