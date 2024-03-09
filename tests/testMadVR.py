# # pylint: disable=protected-access, missing-function-docstring, missing-class-docstring, invalid-name, missing-module-docstring

import unittest
import os
from madvr.madvr import Madvr

# import time

madvr = Madvr(host="192.168.88.38", port=44077)

# write a class to test the madvr class
class TestMadvr(unittest.IsolatedAsyncioTestCase):
    async def test_process_info(self):
        """Verify the process info func works to assign attrs, with modifications"""
        await madvr._process_notifications(
            'Welcome\r\nOk\r\nIncomingSignalInfo 3840x2160 23.976p 2D 422 10bit HDR10 2020 TV 16:9\r\nAspectRatio 129x123 1.78 178 "TV"\r\nOutgoingSignalInfo 3840x2160 23.976p 2D 444 12bit HDR10 2020 TV\r\n'
        )
        # pretend like we got a new signal
        await madvr._process_notifications(
            "IncomingSignalInfo 4096x2160 60p 2D 444 12bit HDR10 2020 TV 16:9\r\n"
        )
        self.assertEqual(
            madvr.msg_dict,
            {
                "incoming_res": "4096x2160",
                "incoming_frame_rate": "60p",
                "incoming_color_space": "444",
                "incoming_bit_depth": "12bit",
                "is_signal": True,
                "hdr_flag": True,
                "incoming_colorimetry": "2020",
                "incoming_black_levels": "TV",
                "incoming_aspect_ratio": "16:9",
                "aspect_res": "129x123",
                "aspect_dec": 1.78,
                "aspect_int": "178",
                "aspect_name": '"TV"',
                "outgoing_res": "3840x2160",
                "outgoing_frame_rate": "23.976p",
                "outgoing_color_space": "444",
                "outgoing_bit_depth": "12bit",
                "outgoing_hdr_flag": True,
                "outgoing_colorimetry": "2020",
                "outgoing_black_levels": "TV",
            },
        )
    async def test_send_command(self):
        """Verify the send command func works"""
        await madvr.send_command(["GetIncomingSignalInfo"])
        await madvr.read_notifications()
        # s = await madvr.send_command(["GetAspectRatio"])

        print(madvr.msg_dict)
