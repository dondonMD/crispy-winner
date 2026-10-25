"""In-memory library mechanisms, NOT reproduction of the WSL network failure."""

import asyncio
import time

from websockets.asyncio.connection import Connection
from websockets.frames import Frame, OP_PONG, OP_TEXT
from websockets.protocol import CLIENT, Protocol


class MemoryTransport:
    """A bounded synthetic read gate; never opens a socket."""

    def __init__(self):
        self.paused = False

    def pause_reading(self):
        self.paused = True

    def resume_reading(self):
        self.paused = False

    def set_write_buffer_limits(self, high, low):
        pass

    def write(self, data):
        pass

    def is_closing(self):
        return False


def connection():
    ws = Connection(Protocol(CLIENT), max_queue=16)
    transport = MemoryTransport()
    ws.connection_made(transport)
    return ws, transport


def test_pong_processed_without_application_recv():
    async def run():
        ws, _ = connection()
        waiter = await ws.ping(b"fixed")
        ws.data_received(Frame(OP_PONG, b"fixed").serialize(mask=False))
        assert waiter.done() and waiter.result() >= 0
        assert not ws.pending_pings
    asyncio.run(run())


def test_paused_transport_can_defer_a_later_pong_until_frames_drained():
    async def run():
        ws, transport = connection()
        waiter = await ws.ping(b"fixed")
        ws.data_received(b"".join(Frame(OP_TEXT, b"x").serialize(mask=False) for _ in range(17)))
        assert transport.paused and len(ws.recv_messages.frames) == 17
        assert ws.recv_messages.low == 4
        # A real paused transport doesn't invoke data_received for later reads.
        # Model that gate explicitly rather than claiming a real server timed out.
        pong = Frame(OP_PONG, b"fixed").serialize(mask=False)
        if not transport.paused:
            ws.data_received(pong)
        assert not waiter.done()
        for _ in range(13):
            assert await ws.recv() == "x"
        assert not transport.paused and len(ws.recv_messages.frames) == 4
        ws.data_received(pong)
        assert waiter.done()
    asyncio.run(run())


def test_pong_already_in_same_read_is_not_blocked_by_frame_queue():
    async def run():
        ws, transport = connection()
        waiter = await ws.ping(b"fixed")
        packet = b"".join(Frame(OP_TEXT, b"x").serialize(mask=False) for _ in range(17))
        packet += Frame(OP_PONG, b"fixed").serialize(mask=False)
        ws.data_received(packet)
        assert transport.paused and waiter.done()
    asyncio.run(run())


def test_synchronous_callback_defers_pong_callback_until_it_yields():
    async def run():
        ws, _ = connection()
        waiter = await ws.ping(b"fixed")
        asyncio.get_running_loop().call_soon(
            ws.data_received, Frame(OP_PONG, b"fixed").serialize(mask=False),
        )
        # Deliberate 30ms test-only blocking, not a production timeout simulation.
        time.sleep(0.03)
        assert not waiter.done()
        await asyncio.sleep(0)
        assert waiter.done()
    asyncio.run(run())
