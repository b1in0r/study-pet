import unittest
import zlib

from studypet.codex_status import CodexStatus
from studypet.screen_protocol import FRAME_SIZE, HEADER, HEIGHT, WIDTH, frame_packet, pack_pixels


class ScreenProtocolTests(unittest.TestCase):
    def test_all_pixels_map_to_distinct_valid_bits(self):
        positions = set()
        for y in range(HEIGHT):
            inv = HEIGHT - 1 - y
            for x in range(WIDTH):
                position = ((x >> 1) * (HEIGHT >> 2) + (inv >> 2), 7 - ((inv & 3) * 2 + (x & 1)))
                self.assertLess(position[0], FRAME_SIZE)
                positions.add(position)
        self.assertEqual(len(positions), WIDTH * HEIGHT)

    def test_frame_crc_and_header(self):
        frame = pack_pixels([1] * (WIDTH * HEIGHT))
        self.assertEqual(frame, b'\xff' * FRAME_SIZE)
        packet = frame_packet(1, frame)
        self.assertEqual(HEADER.unpack(packet[:16]), (b'SPET', 1, 1, 1, FRAME_SIZE, zlib.crc32(frame)))
        self.assertEqual(packet[16:], frame)

    def test_corner_orientation(self):
        pixels = [0] * (WIDTH * HEIGHT)
        pixels[0] = pixels[-1] = 1
        frame = pack_pixels(pixels)
        self.assertEqual(frame[74], 2)
        self.assertEqual(frame[-75], 64)
        self.assertEqual(sum(byte.bit_count() for byte in frame), 2)

    def test_reject_wrong_size_and_page(self):
        with self.assertRaises(ValueError):
            frame_packet(2, b'\0' * FRAME_SIZE)
        with self.assertRaises(ValueError):
            pack_pixels([0])


class CodexSnapshotTests(unittest.TestCase):
    def test_only_completed_reply_is_displayed(self):
        client = CodexStatus.__new__(CodexStatus)
        def request(method, params=None):
            if method == 'account/rateLimits/read':
                return {'rateLimitsByLimitId': {'codex': {'primary': {'usedPercent': 41}}}}
            return {'data': [
                {'item': {'type': 'reasoning', 'content': 'must not display'}},
                {'item': {'type': 'agentMessage', 'phase': 'commentary', 'text': 'progress'}},
                {'item': {'type': 'agentMessage', 'phase': 'final_answer', 'questions': ['question'], 'text': 'question'}},
                {'item': {'type': 'agentMessage', 'phase': 'final_answer', 'text': 'completed reply'}},
            ]}
        client.request = request
        snapshot = client.snapshot('selected-thread')
        self.assertEqual(snapshot['reply'], 'completed reply')
        self.assertEqual(snapshot['limits']['primary']['usedPercent'], 41)

    def test_no_thread_does_not_read_other_chats(self):
        client = CodexStatus.__new__(CodexStatus)
        calls = []
        def request(method, params=None):
            calls.append(method)
            return {'rateLimits': {}}
        client.request = request
        self.assertEqual(client.snapshot()['reply_error'], '未选择 Codex 对话')
        self.assertEqual(calls, ['account/rateLimits/read'])


if __name__ == '__main__':
    unittest.main()
