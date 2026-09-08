"""Offline Control Center tests: fake services and ephemeral aiohttp sockets only."""
import ast
import asyncio
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer
from bot.control_center import ControlCenterServer, ControlCenterSettings, OwnedStatus, DashboardStatus

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'offline-test-password-only'


class SettingsTests(unittest.TestCase):
    def test_loopback_default_and_dedicated_port(self):
        settings = ControlCenterSettings(password=PASSWORD)
        settings.validate()
        self.assertEqual((settings.host, settings.port), ('127.0.0.1', 8090))
        self.assertNotIn(PASSWORD, repr(settings))

    def test_overlay_port_collision_refused(self):
        for port in (8080, 8081, 8082):
            with self.assertRaises(ValueError):
                ControlCenterSettings(port=port).validate_overlay_port('8080')
        ControlCenterSettings().validate_overlay_port('invalid')

    def test_bad_settings_fail_closed(self):
        for host in ('0.0.0.0', '::', '::1', 'localhost', '192.168.1.2', '127.0.0.1.evil'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                ControlCenterServer(ControlCenterSettings(host=host, password=PASSWORD), Mock())
        for password in ('', 'short', ' ' * 20, None, 'a' * 1025):
            with self.subTest(kind=type(password)), self.assertRaises(ValueError):
                ControlCenterServer(ControlCenterSettings(password=password), Mock())
        for port in (0, -1, 65536, True, '8090'):
            with self.assertRaises(ValueError):
                ControlCenterSettings(port=port, password=PASSWORD).validate()

    def test_environment_convention_without_real_environment(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(ValueError):
                ControlCenterSettings.from_env().validate()
        with patch.dict('os.environ', {'CONTROL_CENTER_PORT':'bad'}, clear=True):
            self.assertEqual(ControlCenterSettings.from_env().port, -1)
        with patch.dict('os.environ', {'CONTROL_CENTER_PORT':'8099','CONTROL_CENTER_PASSWORD':PASSWORD}, clear=True):
            settings = ControlCenterSettings.from_env()
            settings.validate()
            self.assertEqual(settings.port, 8099)


class StatusTests(unittest.TestCase):
    def test_typed_selected_serialization(self):
        secret = 'DO-NOT-SERIALIZE'
        twitch = SimpleNamespace(connected_channels=[SimpleNamespace(name='channel_one'), SimpleNamespace(name='<script>')], token=secret)
        other = SimpleNamespace(config={'api_key':secret}, exception=RuntimeError(secret))
        status = OwnedStatus(twitch, other, other, other)()
        self.assertIsInstance(status, DashboardStatus)
        payload = json.loads(json.dumps(status.to_dict()))
        self.assertEqual(set(payload), {'schema_version','meangene','channels','services'})
        self.assertEqual(payload['channels'], ['channel_one'])
        self.assertEqual(payload['meangene'], 'unknown')
        self.assertEqual(payload['services'][0]['state'], 'channels_joined')
        self.assertNotIn(secret, json.dumps(payload))
        self.assertNotIn('config', json.dumps(payload))
        for service in status.services[:3]:
            self.assertFalse(service.reconnect.supported)
            self.assertTrue(service.reconnect.reason)

    def test_missing_evidence_and_services(self):
        for status in OwnedStatus(object(), object(), object(), object())().services:
            self.assertEqual(status.state, 'unknown')
        for status in OwnedStatus(None, None, None, None)().services:
            self.assertEqual(status.state, 'unavailable')

    def test_exception_details_sanitized(self):
        class Broken:
            @property
            def connected_channels(self):
                raise RuntimeError('private failure')
        payload = json.dumps(OwnedStatus(Broken(), None, None, None)().to_dict())
        self.assertNotIn('private failure', payload)


class HTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 10
        self.provider = Mock(return_value=OwnedStatus(None, None, None, None)())
        self.server = ControlCenterServer(ControlCenterSettings(password=PASSWORD), self.provider, clock=lambda:self.now)
        self.client = TestClient(TestServer(self.server.app), cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server()
        self.headers = {'Host':'127.0.0.1:8090'}
        self.mutation = {**self.headers, 'Origin':'http://127.0.0.1:8090'}

    async def asyncTearDown(self):
        await self.client.close()
        await self.server.close()

    async def login_session(self):
        response = await self.client.get('/control/login', headers=self.headers)
        csrf = re.search(r'data-csrf="([^"]+)"', await response.text())[1]
        cookie = response.cookies[self.server.COOKIE]
        return csrf, cookie

    async def authenticate(self):
        csrf, cookie = await self.login_session()
        response = await self.client.post('/control/login', headers={**self.mutation,'X-CSRF-Token':csrf}, json={'password':PASSWORD})
        self.assertEqual(response.status, 200)
        self.assertNotEqual(response.cookies[self.server.COOKIE].value, cookie.value)
        status = await self.client.get('/control/api/status', headers=self.headers)
        return (await status.json())['csrf']

    async def test_success_and_cookie_security(self):
        _, cookie = await self.login_session()
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Strict')
        self.assertEqual(cookie['path'], '/control/')
        self.assertFalse(cookie['secure'])
        # Discard the first pre-login cookie to exercise session rotation afresh.
        self.client.session.cookie_jar.clear()
        csrf = await self.authenticate()
        response = await self.client.get('/control/', headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        self.assertNotIn(PASSWORD, await response.text())
        self.assertTrue(csrf)

    async def test_failed_authentication(self):
        csrf, _ = await self.login_session()
        response = await self.client.post('/control/login', headers={**self.mutation,'X-CSRF-Token':csrf}, json={'password':'incorrect'})
        self.assertEqual(response.status, 401)
        self.assertFalse(self.server.sessions)

    async def test_protected_content_and_mutations(self):
        for path in ('/control/', '/control/api/status', '/control/assets/dashboard.js'):
            response = await self.client.get(path, headers=self.headers)
            self.assertEqual(response.status, 401)
        for path in ('/control/logout','/control/api/reconnect/twitch'):
            response = await self.client.post(path, headers=self.mutation, json={})
            self.assertEqual(response.status, 401)
        self.provider.assert_not_called()

    async def test_login_requires_origin_and_csrf(self):
        csrf, _ = await self.login_session()
        for headers in (self.headers, self.mutation, {**self.mutation,'X-CSRF-Token':'bad'},
                        {**self.headers,'Origin':'http://evil.test','X-CSRF-Token':csrf}):
            response = await self.client.post('/control/login', headers=headers, json={'password':PASSWORD})
            self.assertEqual(response.status, 403)

    async def test_mutation_security_matrix(self):
        csrf = await self.authenticate()
        for path in ('/control/logout','/control/api/reconnect/twitch', '/control/api/reconnect/discord','/control/api/reconnect/hermes'):
            for origin in (None, 'null', 'http://evil.test', 'http://127.0.0.1:8080', 'http://localhost:8090', 'http://127.0.0.1:8090/'):
                headers = {**self.headers,'X-CSRF-Token':csrf}
                if origin is not None:
                    headers['Origin'] = origin
                response = await self.client.post(path, headers=headers, json={})
                self.assertEqual(response.status, 403)
            for token in ('', 'invalid'):
                response = await self.client.post(path, headers={**self.mutation,'X-CSRF-Token':token}, json={})
                self.assertEqual(response.status, 403)

    async def test_malformed_mutations(self):
        csrf = await self.authenticate()
        headers = {**self.mutation,'X-CSRF-Token':csrf}
        for body in ('not json', '[]', 'null'):
            response = await self.client.post('/control/logout', headers={**headers,'Content-Type':'application/json'}, data=body)
            self.assertEqual(response.status, 400)
        response = await self.client.post('/control/logout', headers=headers, data='{}')
        self.assertEqual(response.status, 400)
        response = await self.client.post('/control/logout', headers=headers, json={'extra':1})
        self.assertEqual(response.status, 400)

    async def test_logout_invalidates_server_session(self):
        csrf = await self.authenticate()
        old = next(key for key, value in self.server.sessions.items() if value.authenticated)
        response = await self.client.post('/control/logout', headers={**self.mutation,'X-CSRF-Token':csrf}, json={})
        self.assertEqual(response.status, 200)
        self.assertNotIn(old, self.server.sessions)
        response = await self.client.get('/control/api/status', headers={**self.headers,'Cookie':f'{self.server.COOKIE}={old}'})
        self.assertEqual(response.status, 401)

    async def test_login_get_does_not_log_out_authenticated_session(self):
        await self.authenticate()
        keys = set(self.server.sessions)
        response = await self.client.get('/control/login', headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(keys, set(self.server.sessions))
        response = await self.client.get('/control/api/status', headers=self.headers)
        self.assertEqual(response.status, 200)

    async def test_expiry(self):
        await self.authenticate()
        self.now += 3601
        response = await self.client.get('/control/api/status', headers=self.headers)
        self.assertEqual(response.status, 401)

    async def test_unsupported_reconnect_no_lifecycle_calls(self):
        csrf = await self.authenticate()
        for service in ('twitch','discord','hermes'):
            response = await self.client.post('/control/api/reconnect/'+service, headers={**self.mutation,'X-CSRF-Token':csrf}, json={})
            self.assertEqual(response.status, 409)
            self.assertFalse((await response.json())['supported'])
        self.assertEqual(self.provider.call_count, 1)  # Authentication helper's GET only.

    async def test_host_check_and_sanitized_failure(self):
        response = await self.client.get('/control/login', headers={'Host':'evil.test'})
        self.assertEqual(response.status, 403)
        await self.authenticate()
        self.provider.side_effect = RuntimeError('SECRET-EXCEPTION')
        response = await self.client.get('/control/api/status', headers=self.headers)
        self.assertEqual(response.status, 500)
        self.assertNotIn('SECRET-EXCEPTION', await response.text())

    async def test_navigation_and_placeholder_pages(self):
        await self.authenticate()
        response = await self.client.get('/control/', headers=self.headers)
        html = await response.text()
        for destination in ('dashboard','commands','wheel','raffle','lore','hermes','audio-media','logs','settings'):
            self.assertIn('href="#'+destination+'"', html)
        response = await self.client.get('/control/assets/dashboard.js', headers=self.headers)
        js = await response.text()
        self.assertIn('Sprint 1 placeholder', js)
        self.assertIn('Read-only', js)
        self.assertIn('button.disabled = true', js)
        self.assertNotIn('innerHTML', js)


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_close_and_repeat(self):
        server = ControlCenterServer(ControlCenterSettings(password=PASSWORD), Mock())
        runner = SimpleNamespace(setup=AsyncMock(), cleanup=AsyncMock())
        site = SimpleNamespace(start=AsyncMock())
        with patch('bot.control_center.web.AppRunner', return_value=runner), patch('bot.control_center.web.TCPSite', return_value=site) as factory:
            await server.start()
            factory.assert_called_once_with(runner,'127.0.0.1',8090)
            with self.assertRaises(RuntimeError):
                await server.start()
            await server.close()
            await server.close()
        runner.cleanup.assert_awaited_once()
        self.assertIsNone(server.runner)

    async def test_partial_startup_original_failure_survives_cleanup(self):
        for stage in ('setup','bind'):
            for cleanup_fails in (False, True):
                server = ControlCenterServer(ControlCenterSettings(password=PASSWORD), Mock())
                original = OSError('startup')
                runner = SimpleNamespace(setup=AsyncMock(side_effect=original if stage=='setup' else None), cleanup=AsyncMock(side_effect=RuntimeError('cleanup') if cleanup_fails else None))
                site = SimpleNamespace(start=AsyncMock(side_effect=original if stage=='bind' else None))
                with patch('bot.control_center.web.AppRunner', return_value=runner), patch('bot.control_center.web.TCPSite', return_value=site):
                    with self.assertRaises(OSError) as caught:
                        await server.start()
                self.assertIs(caught.exception, original)
                runner.cleanup.assert_awaited_once()
                self.assertIsNone(server.runner)

    async def test_real_ephemeral_listener_closes(self):
        server = ControlCenterServer(ControlCenterSettings(password=PASSWORD), Mock())
        real_site = web.TCPSite
        sites = []
        def ephemeral(runner, host, port):
            site = real_site(runner, host, 0)
            sites.append(site)
            return site
        with patch('bot.control_center.web.TCPSite', side_effect=ephemeral):
            await server.start()
        runner = server.runner
        self.assertTrue(runner.addresses)
        await server.close()
        self.assertFalse(runner.addresses)
        self.assertFalse(runner.sites)

    async def test_cancellation_during_setup(self):
        server = ControlCenterServer(ControlCenterSettings(password=PASSWORD), Mock())
        runner = SimpleNamespace(setup=AsyncMock(side_effect=asyncio.CancelledError), cleanup=AsyncMock())
        with patch('bot.control_center.web.AppRunner', return_value=runner):
            with self.assertRaises(asyncio.CancelledError):
                await server.start()
        runner.cleanup.assert_awaited_once()

    async def test_composition_root_executes_owned_injection_and_cleanup(self):
        await self.exercise_root_failure(False)

    async def test_composition_root_cleans_center_after_later_startup_failure(self):
        await self.exercise_root_failure(True)

    async def exercise_root_failure(self, after_center):
        # Extract the real main body; replace every runtime boundary before execution.
        tree = ast.parse((ROOT/'bot/main.py').read_text(encoding='utf-8'))
        main = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name=='main')
        # Execute from resource initialization through the outer cleanup guard.
        index = next(i for i,n in enumerate(main.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='overlay_task' for t in n.targets))
        main.body = main.body[index:]
        original = OSError('offline bind failure')
        center = SimpleNamespace(start=AsyncMock(side_effect=None if after_center else original), close=AsyncMock(side_effect=RuntimeError('cleanup failure')))
        bot = SimpleNamespace(hermes_bridge=SimpleNamespace(settings=SimpleNamespace(enabled=False)), lore_store=object(), lore_capture=SimpleNamespace(settings=object(),_moderation_poster=None),close=AsyncMock())
        bot.ticker_cycle_task = Mock(side_effect=original)
        async def overlay():
            await asyncio.Event().wait()
        factory = Mock(return_value=center)
        ns = dict(asyncio=asyncio, logging=Mock(), os=SimpleNamespace(getenv=lambda key, default:default), start_overlay_server_resilient=overlay,
                  create_bot=Mock(return_value=bot), DiscordOperatorSettings=SimpleNamespace(from_env=lambda:SimpleNamespace(enabled=False)),
                  DISCORD_AVAILABLE=False, startup_diagnostics=Mock(), ControlCenterSettings=SimpleNamespace(from_env=lambda:ControlCenterSettings(password=PASSWORD)),
                  ControlCenterServer=factory, OwnedStatus=OwnedStatus)
        exec(compile(ast.Module(body=[main],type_ignores=[]),'offline_main','exec'),ns)
        with self.assertRaises(OSError) as caught:
            await ns['main']()
        self.assertIs(caught.exception, original)
        factory.assert_called_once()
        adapter = factory.call_args.args[1]
        self.assertIs(adapter.twitch, bot)
        self.assertIs(adapter.hermes, bot.hermes_bridge)
        self.assertIs(adapter.lore, bot.lore_store)
        center.close.assert_awaited_once()
        bot.close.assert_awaited_once()
        ns['create_bot'].assert_called_once()


if __name__ == '__main__':
    unittest.main()
