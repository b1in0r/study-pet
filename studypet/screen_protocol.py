"""Versioned USB frame format; independent of optional display packages."""
import struct
import zlib

WIDTH, HEIGHT = 400, 300
FRAME_SIZE = WIDTH * HEIGHT // 8
HEADER = struct.Struct('<4sBBHII')


def pack_pixels(pixels) -> bytes:
    """Pack row-major white(1)/black(0) pixels into Waveshare's ST7305 layout."""
    if len(pixels) != WIDTH * HEIGHT:
        raise ValueError('Expected 400 x 300 pixels')
    result = bytearray(FRAME_SIZE)
    for y in range(HEIGHT):
        inverted = HEIGHT - 1 - y
        block, local_y = inverted >> 2, inverted & 3
        for x in range(WIDTH):
            if pixels[y * WIDTH + x]:
                index = (x >> 1) * (HEIGHT >> 2) + block
                bit = 7 - (local_y * 2 + (x & 1))
                result[index] |= 1 << bit
    return bytes(result)


def frame_packet(page: int, frame: bytes) -> bytes:
    if page not in (0, 1) or len(frame) != FRAME_SIZE:
        raise ValueError('Invalid page or frame size')
    return HEADER.pack(b'SPET', 1, 1, page, len(frame), zlib.crc32(frame)) + frame
