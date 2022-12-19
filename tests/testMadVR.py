import unittest
import os
from dotenv import load_dotenv
from madvr.madvr import Madvr
import asyncio

# load .env
load_dotenv()

host = os.getenv("MADVR_HOST")

madvr = Madvr(host=host, connect_timeout=10)

class TestMenu(unittest.TestCase):
    def test_02lowlat(self):
        out = asyncio.run(
            madvr.async_send_command("PowerOff\r\n")
        )
        print(out)

if __name__ == '__main__':
    unittest.main()

    