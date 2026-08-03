import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import bot.wot_api as wot_api
from bot.wot_api import WotApiClient, WotConfig, load_wot_auth, save_wot_auth


class WotAuthTests(unittest.TestCase):
    def setUp(self):
        self.original_auth_file = wot_api.AUTH_FILE
        self.temp_dir = tempfile.TemporaryDirectory()
        wot_api.AUTH_FILE = Path(self.temp_dir.name) / "wot_auth.json"

    def tearDown(self):
        wot_api.AUTH_FILE = self.original_auth_file
        self.temp_dir.cleanup()

    def test_token_is_stored_and_loaded_locally(self):
        save_wot_auth(
            {
                "access_token": "secret-token",
                "account_id": "9546892",
                "nickname": "Darr-x",
                "untrusted": "discard me",
            }
        )
        self.assertEqual(
            {
                "access_token": "secret-token",
                "account_id": "9546892",
                "nickname": "Darr-x",
            },
            load_wot_auth(),
        )

    def test_login_url_comes_from_api_location(self):
        client = WotApiClient(WotConfig("app"), None)
        client._get = AsyncMock(return_value={"location": "https://login.example/"})
        self.assertEqual(
            "https://login.example/",
            __import__("asyncio").run(client.login_url("http://localhost/callback")),
        )

