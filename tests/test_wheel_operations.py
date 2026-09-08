"""Offline Wheel contracts: real state, command callbacks and WebSocket dispatch."""
import json
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bot import overlay_server
from bot.commands import wheel_cog
from bot.wheel_state import WheelState, get_wheel_state, apply_wheel_control, WheelOperationError


class WheelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'wheel.json'
        self.state = get_wheel_state(self.path)
        self.state.add_slots('alice', 2, allow_multi=True, color='#123456')
        self.state.add_slots('manual', 7, allow_multi=True, manual=True)
        self.addCleanup(__import__("bot.wheel_state", fromlist=["_states"])._states.pop, str(self.path.resolve()).lower(), None)
        self.cog = wheel_cog.WheelCog.__new__(wheel_cog.WheelCog)
        self.cog.state = self.state

    def persisted(self):
        return json.loads(self.path.read_text())

    async def command(self, name, text, user='alice'):
        ctx = SimpleNamespace(message=SimpleNamespace(content=text),
                              author=SimpleNamespace(name=user, is_mod=True, is_broadcaster=True),
                              send=AsyncMock())
        command = getattr(wheel_cog.WheelCog, name)
        with patch.object(wheel_cog, 'broadcast_overlay_message', new_callable=AsyncMock) as broadcast:
            await command._callback(self.cog, ctx)
        return ctx, broadcast

    async def websocket(self, action, value):
        message = SimpleNamespace(type=overlay_server.web.WSMsgType.TEXT,
                                  data=json.dumps(dict(type='wheel_control', action=action, value=value)))
        class Socket:
            prepare = AsyncMock()
            send_json = AsyncMock()
            def __aiter__(self):
                async def messages():
                    yield message
                return messages()
        ws = Socket()
        with patch.object(overlay_server.web, 'WebSocketResponse', return_value=ws), patch.object(
            overlay_server, 'WHEEL_STATE_FILE', str(self.path)
        ), patch.object(overlay_server, 'broadcast_overlay_message', new_callable=AsyncMock) as broadcast:
            await overlay_server.websocket_handler(None)
        self.socket = ws
        return broadcast

    async def test_websocket_multiplier_updates_configuration_and_live_object(self):
        self.state.set_multiplier(3)
        broadcast = await self.websocket('set_multiplier', 5)
        self.assertIs(self.state, get_wheel_state(self.path))
        self.assertEqual({'alice': 5, 'manual': 5}, self.state.slots)
        self.assertEqual(5, self.state.multiplier)
        self.assertEqual({'manual'}, self.state.manual_users)
        self.assertEqual(self.state.slots, self.persisted()['slots'])
        broadcast.assert_awaited_once_with(self.state.get_state_payload())
        self.assertTrue(self.state.join('future'))
        self.assertEqual(self.state.multiplier, self.state.slots['future'])

    async def test_configured_multiplier_and_join_match_persistence_and_message(self):
        await self.command('wheel_multiplier', '!wheelmultiplier 4')
        self.assertEqual({'alice': 4, 'manual': 4}, self.state.slots)
        ctx, broadcast = await self.command('wheel_join', '!wheeljoin', 'future')
        self.assertEqual(self.state.multiplier, self.state.slots['future'])
        self.assertIn('4 slots', ctx.send.call_args.args[0])
        self.assertEqual(4, WheelState(self.path).multiplier)
        self.assertEqual(self.state.slots, WheelState(self.path).slots)
        broadcast.assert_awaited_once_with(self.state.get_state_payload())
        before = self.path.read_bytes()
        self.assertFalse(self.state.join('FUTURE'))
        self.state.set_wheel_locked(True)
        before = self.path.read_bytes()
        self.assertFalse(self.state.join('locked'))
        self.assertEqual(before, self.path.read_bytes())

    async def test_remove_on_win_both_transports_same_live_and_disk_result(self):
        await self.command('wheel_remove_on_win', '!wheelremoveonwin on')
        twitch = self.persisted()
        self.state.set_remove_on_win(False)
        broadcast = await self.websocket('set_remove_on_win', True)
        self.assertEqual(twitch, self.persisted())
        self.assertTrue(self.state.remove_on_win)
        broadcast.assert_awaited_once_with(self.state.get_state_payload())

    async def test_individual_add_color_remove_preserve_other_users_and_settings(self):
        self.state.set_multiplier(3)
        await self.command('wheel_add', '!wheeladd bob 8 #abcdef')
        self.assertEqual(3, self.state.slots['bob'])
        self.assertIn('bob', self.state.manual_users)
        await self.command('wheel_color', '!wheelcolor #112233', 'bob')
        self.assertEqual('#112233', self.persisted()['colors']['bob'])
        await self.command('wheel_remove', '!wheelremove bob')
        self.assertNotIn('bob', self.state.slots)
        self.assertNotIn('bob', self.state.order)
        self.assertNotIn('bob', self.state.manual_users)
        self.assertEqual({'alice': 3, 'manual': 3}, self.state.slots)
        self.assertEqual(3, self.persisted()['multiplier'])

    async def test_websocket_invalid_counts_and_empty_configuration(self):
        for value in (None, 'bad', -4, 900, True, 1.5, '1.5'):
            before = copy.deepcopy(self.state.__dict__)
            disk = self.path.read_bytes()
            with self.assertLogs(level='ERROR'):
                broadcast = await self.websocket('set_multiplier', value)
            broadcast.assert_not_awaited()
            self.assertEqual('wheel_error', self.socket.send_json.call_args.args[0]['type'])
            self.assertEqual(before, self.state.__dict__)
            self.assertEqual(disk, self.path.read_bytes())
        self.assertFalse(apply_wheel_control(self.state, 'set_slot_count', 3))
        self.state.reset()
        await self.websocket('set_multiplier', ' 008 ')
        self.assertEqual({}, self.state.slots)
        self.assertEqual(8, self.persisted()['multiplier'])

    async def test_unknown_fields_survive_websocket_and_twitch(self):
        data = self.persisted()
        data['future'] = {'nested': [1, 2]}
        self.path.write_text(json.dumps(data))
        await self.websocket('set_multiplier', 2)
        await self.command('wheel_multiplier', '!wheelmultiplier 4')
        self.assertEqual(data['future'], self.persisted()['future'])

    async def test_spin_decrements_one_slot_without_reconfiguring_multiplier(self):
        self.state.set_multiplier(3)
        await self.websocket('set_remove_on_win', True)
        self.state.set_wheel_locked(True)
        with patch('bot.wheel_state.random.randrange', return_value=0):
            winner, index, slots = self.state.spin()
        self.assertEqual(('alice', 0), (winner, index))
        self.assertEqual(3, slots.count('alice'))
        self.assertEqual(2, self.state.slots['alice'])
        self.assertEqual(3, self.state.multiplier)
        self.assertEqual(1, self.persisted()['scores']['alice'])
        self.assertEqual(self.state.get_state_payload(), WheelState(self.path).get_state_payload())

    async def test_websocket_all_counts_matches_direct_operation(self):
        self.state.set_all_counts(9)
        expected = self.persisted()
        self.state.set_all_counts(2)
        await self.websocket('set_multiplier', 9)
        self.assertEqual(expected, self.persisted())

    async def test_twitch_boundaries_and_invalid_input_do_not_write_or_broadcast(self):
        for value in ('0', '501', '-1', 'bad', '1.5'):
            before = self.path.read_bytes()
            with self.assertLogs(level='ERROR'):
                ctx, broadcast = await self.command('wheel_multiplier', '!wheelmultiplier ' + value)
            self.assertEqual(before, self.path.read_bytes())
            broadcast.assert_not_awaited()
        for value in (1, 500):
            await self.command('wheel_multiplier', f'!wheelmultiplier {value}')
            self.assertEqual(value, self.state.multiplier)
            self.assertEqual(value, self.persisted()['multiplier'])
        for value in ('0', '501', 'bad'):
            before = self.path.read_bytes()
            _, broadcast = await self.command('wheel_add', '!wheeladd bob ' + value)
            broadcast.assert_not_awaited()
            self.assertEqual(before, self.path.read_bytes())

    async def test_authoritative_count_validation(self):
        for method in (self.state.set_multiplier, self.state.set_all_counts,
                       lambda count: self.state.add_slots('bob', count, manual=True)):
            for value in (0, 501, -1, None, 'bad', True, 1.5):
                before = copy.deepcopy(self.state.__dict__)
                disk = self.path.read_bytes()
                with self.assertRaises(ValueError):
                    method(value)
                self.assertEqual(before, self.state.__dict__)
                self.assertEqual(disk, self.path.read_bytes())

    async def test_both_callers_report_replace_failure_without_success_or_mutation(self):
        for caller in ('twitch', 'websocket'):
            before = copy.deepcopy(self.state.__dict__)
            disk = self.path.read_bytes()
            slots = self.state.slots
            with self.assertLogs(level='ERROR'), patch('bot.wheel_state.os.replace', side_effect=OSError('disk unavailable')):
                if caller == 'twitch':
                    ctx, broadcast = await self.command('wheel_remove_on_win', '!wheelremoveonwin on')
                    self.assertIn('no change was committed', ctx.send.call_args.args[0])
                else:
                    broadcast = await self.websocket('set_remove_on_win', True)
                    self.assertEqual('wheel_error', self.socket.send_json.call_args.args[0]['type'])
            broadcast.assert_not_awaited()
            self.assertEqual(before, self.state.__dict__)
            self.assertEqual(disk, self.path.read_bytes())
            self.assertEqual(before['slots'], slots)
            self.assertEqual([self.path], list(self.path.parent.iterdir()))

    async def test_all_mutations_are_staged_on_serialization_failure(self):
        operations = [lambda: self.state.join('bob'),
                      lambda: self.state.add_slots('bob', 5, manual=True),
                      lambda: self.state.remove_user('alice'),
                      lambda: self.state.set_color('alice', '#abcdef'),
                      lambda: self.state.set_multiplier(4),
                      lambda: self.state.set_all_counts(4),
                      lambda: self.state.set_remove_on_win(True),
                      lambda: self.state.set_wheel_locked(True),
                      lambda: self.state.set_last_man_standing(True),
                      self.state.reset, self.state.spin]
        for operation in operations:
            before = copy.deepcopy(self.state.__dict__)
            disk = self.path.read_bytes()
            with patch('bot.wheel_state.json.dump', side_effect=OSError('short write')):
                with self.assertRaises(WheelOperationError):
                    operation()
            self.assertEqual(before, self.state.__dict__)
            self.assertEqual(disk, self.path.read_bytes())
            self.assertEqual([self.path], list(self.path.parent.iterdir()))

    async def test_shared_boolean_normalization(self):
        for value, expected in ((False, False), (True, True), ('false', False),
                                (' ON ', True), (0, False), (1, True)):
            await self.websocket('set_remove_on_win', value)
            self.assertEqual(expected, self.state.remove_on_win)
            self.assertEqual(expected, self.persisted()['remove_on_win'])
        for method in (self.state.set_remove_on_win, self.state.set_wheel_locked,
                       self.state.set_last_man_standing):
            for value in (None, '', 'nonsense', 2, 1.5):
                with self.assertRaises(WheelOperationError):
                    method(value)
        before = self.path.read_bytes()
        _, broadcast = await self.command('wheel_remove_on_win', '!wheelremoveonwin nonsense')
        broadcast.assert_not_awaited()
        self.assertEqual(before, self.path.read_bytes())

    async def test_manual_add_cannot_bypass_duplicate_or_lock_checks(self):
        before = self.path.read_bytes()
        self.assertFalse(self.state.add_slots('ALICE', 2, allow_multi=True, manual=True))
        self.assertEqual(before, self.path.read_bytes())
        self.state.set_wheel_locked(True)
        self.assertFalse(self.state.add_slots('bob', 2, allow_multi=True, manual=True))
        self.assertNotIn('bob', self.persisted()['slots'])

    async def test_color_validation_and_successful_mutation_reload_agreement(self):
        before = self.path.read_bytes()
        with self.assertRaises(WheelOperationError):
            self.state.set_color('alice', 'invalid')
        self.assertEqual(before, self.path.read_bytes())
        for name, text in [('wheel_color', '!wheelcolor bad'),
                           ('wheel_join', '!wheeljoin 0'),
                           ('wheel_join', '!wheeljoin 2')]:
            _, broadcast = await self.command(name, text, 'new')
            broadcast.assert_not_awaited()
            self.assertEqual(before, self.path.read_bytes())
        operations = [lambda: self.state.set_color('alice', 'ABCDEF'),
                      lambda: self.state.set_last_man_standing(True),
                      lambda: self.state.set_wheel_locked(True),
                      lambda: self.state.set_wheel_locked(False),
                      lambda: self.state.set_last_man_standing(False),
                      self.state.spin, self.state.reset]
        for operation in operations:
            operation()
            self.assertEqual(self.state.__dict__, WheelState(self.state.state_file).__dict__)

    async def test_corrupt_refresh_preserves_live_state_and_file(self):
        before = copy.deepcopy(self.state.__dict__)
        self.path.write_text('{"slots": {"alice": "invalid"}}')
        disk = self.path.read_bytes()
        with self.assertRaises(WheelOperationError):
            self.state.set_multiplier(3)
        self.assertEqual(before, self.state.__dict__)
        self.assertEqual(disk, self.path.read_bytes())

    async def test_delivery_failure_is_not_reported_as_commit_failure(self):
        ctx = SimpleNamespace(message=SimpleNamespace(content='!wheelmultiplier 3'),
                              author=SimpleNamespace(name='alice', is_mod=True, is_broadcaster=True),
                              send=AsyncMock())
        with patch.object(wheel_cog, 'broadcast_overlay_message', side_effect=OSError('transport')):
            with self.assertRaises(OSError):
                await wheel_cog.WheelCog.wheel_multiplier._callback(self.cog, ctx)
        ctx.send.assert_not_awaited()
        self.assertEqual(3, self.persisted()['multiplier'])
        self.assertEqual(self.state.__dict__, WheelState(self.state.state_file).__dict__)


    async def test_universal_boundaries_and_transport_equivalence(self):
        for count in (1, 5, 500):
            with self.subTest(count=count):
                await self.command('wheel_multiplier', f'!wheelmultiplier {count}')
                expected = self.persisted()
                await self.websocket('set_multiplier', str(count))
                self.assertEqual(expected, self.persisted())
                ctx, broadcast = await self.command('wheel_join', '!wheeljoin', f'join{count}')
                self.assertIn(f'{count} slot', ctx.send.call_args.args[0])
                broadcast.assert_awaited_once_with(self.state.get_state_payload())
                await self.command('wheel_add', f'!wheeladd manual{count} 7')
                self.assertTrue(self.state.join(f'direct{count}'))
                self.assertEqual({count}, set(self.state.slots.values()))
                self.assertEqual(self.state.__dict__, WheelState(self.state.state_file).__dict__)

    async def test_lock_all_entry_paths_unlock_and_reset(self):
        await self.command('wheel_lock', '!wheellock on')
        before = self.path.read_bytes()
        for method, text in (('wheel_join', '!wheeljoin'), ('wheel_add', '!wheeladd bob 5')):
            ctx, broadcast = await self.command(method, text, 'bob')
            self.assertIn('locked', ctx.send.call_args.args[0])
            broadcast.assert_not_awaited()
        self.assertFalse(self.state.join('bob'))
        self.assertFalse(self.state.add_slots('bob', 5, allow_multi=True))
        self.assertFalse(self.state.add_slots('bob', 5, manual=True))
        # The existing WebSocket schema exposes no join, lock or reset action.
        for action in ('join', 'add_slots', 'set_wheel_locked', 'reset'):
            broadcast = await self.websocket(action, 'bob')
            broadcast.assert_not_awaited()
        self.assertEqual(before, self.path.read_bytes())
        await self.command('wheel_lock', '!wheellock off')
        self.assertTrue(self.state.join('unlocked'))
        self.state.set_wheel_locked(True)
        await self.command('wheel_reset', '!wheelreset')
        self.assertFalse(self.state.wheel_locked)
        self.assertEqual(1, self.state.multiplier)
        self.assertTrue(self.state.join('reset'))
        self.assertEqual(self.state.__dict__, WheelState(self.state.state_file).__dict__)

    async def test_set_all_distinct_only_when_locked_and_unlock_restores_counts(self):
        self.state.set_multiplier(5)
        self.state.set_wheel_locked(True)
        self.state.set_all_counts('002')
        self.assertEqual(5, self.state.multiplier)
        self.assertEqual({2}, set(self.state.slots.values()))
        self.state.set_wheel_locked(False)
        self.assertEqual({5}, set(self.state.slots.values()))
        self.state.set_all_counts(' 01 ')
        self.assertEqual(1, self.state.multiplier)
        self.assertTrue(self.state.join('future'))
        self.assertEqual({1}, set(self.state.slots.values()))
        self.assertEqual(self.state.__dict__, WheelState(self.state.state_file).__dict__)

    async def test_failed_refreshing_operation_does_not_expose_disk_snapshot(self):
        before = copy.deepcopy(self.state.__dict__)
        data = self.persisted()
        data['multiplier'] = 5
        data['slots']['alice'] = 3
        self.path.write_text(json.dumps(data))
        disk = self.path.read_bytes()
        for caller in ('twitch', 'websocket'):
            with self.assertLogs(level='ERROR'), patch('bot.wheel_state.os.replace', side_effect=OSError('disk')):
                if caller == 'twitch':
                    _, broadcast = await self.command('wheel_multiplier', '!wheelmultiplier 2')
                else:
                    broadcast = await self.websocket('set_multiplier', 2)
            broadcast.assert_not_awaited()
            self.assertEqual(before, self.state.__dict__)
            self.assertEqual(disk, self.path.read_bytes())

    async def test_publish_only_after_disk_and_live_commit(self):
        original_replace = __import__('os').replace
        before = copy.deepcopy(self.state.__dict__)
        def replace(source, target):
            self.assertEqual(before, self.state.__dict__)
            original_replace(source, target)
        with patch('bot.wheel_state.os.replace', side_effect=replace):
            _, broadcast = await self.command('wheel_multiplier', '!wheelmultiplier 5')
        self.assertEqual(self.state.__dict__, WheelState(self.state.state_file).__dict__)
        broadcast.assert_awaited_once_with(self.state.get_state_payload())
        with patch.object(overlay_server, 'overlay_clients', set()):
            with patch.object(overlay_server, 'latest_wheel_state', None):
                await overlay_server.broadcast_overlay_message(self.state.get_state_payload())
                self.assertEqual(self.state.get_state_payload(), overlay_server.latest_wheel_state)

    async def test_unlock_reconciles_old_counts_atomically(self):
        data = self.persisted()
        data.update(multiplier=5, wheel_locked=True, slots={'alice': 1, 'manual': 7})
        self.path.write_text(json.dumps(data))
        before = copy.deepcopy(self.state.__dict__)
        disk = self.path.read_bytes()
        with patch('bot.wheel_state.os.replace', side_effect=OSError('disk')):
            with self.assertRaises(WheelOperationError):
                self.state.set_wheel_locked(False)
        self.assertEqual(before, self.state.__dict__)
        self.assertEqual(disk, self.path.read_bytes())
        with self.assertLogs(level='ERROR'), patch('bot.wheel_state.os.replace', side_effect=OSError('disk')):
            _, broadcast = await self.command('wheel_lock', '!wheellock off')
        broadcast.assert_not_awaited()
        self.assertEqual(before, self.state.__dict__)
        self.assertEqual(disk, self.path.read_bytes())
        self.state.set_wheel_locked(False)
        self.assertEqual({'alice': 5, 'manual': 5}, self.state.slots)
        self.assertEqual(self.state.slots, self.persisted()['slots'])

    async def test_name_and_color_normalization_and_duplicate_add(self):
        self.assertTrue(self.state.join(' @BOB ', ' ABCDEF '))
        self.assertEqual('#abcdef', self.state.colors['bob'])
        self.assertFalse(self.state.add_slots('BOB', 500, allow_multi=True))
        for user in ('', '@', None, 3):
            with self.assertRaises(WheelOperationError):
                self.state.join(user)

    async def test_each_twitch_mutation_failure_has_no_success_publication(self):
        cases = [('wheel_join', '!wheeljoin', 'new'),
                 ('wheel_add', '!wheeladd new 5', 'alice'),
                 ('wheel_remove', '!wheelremove alice', 'alice'),
                 ('wheel_color', '!wheelcolor #abcdef', 'alice'),
                 ('wheel_multiplier', '!wheelmultiplier 5', 'alice'),
                 ('wheel_lock', '!wheellock on', 'alice'),
                 ('wheel_last_man', '!wheellastman on', 'alice'),
                 ('wheel_remove_on_win', '!wheelremoveonwin on', 'alice'),
                 ('wheel_reset', '!wheelreset', 'alice'),
                 ('wheel_spin', '!wheelspin', 'alice')]
        for name, text, user in cases:
            with self.subTest(command=name):
                before = copy.deepcopy(self.state.__dict__)
                disk = self.path.read_bytes()
                with patch.object(overlay_server, 'latest_wheel_state', {'sentinel': True}):
                    with self.assertLogs(level='ERROR'), patch('bot.wheel_state.os.replace', side_effect=OSError('disk')):
                        ctx, broadcast = await self.command(name, text, user)
                    self.assertEqual({'sentinel': True}, overlay_server.latest_wheel_state)
                broadcast.assert_not_awaited()
                self.assertIn('no change was committed', ctx.send.call_args.args[0])
                self.assertEqual(before, self.state.__dict__)
                self.assertEqual(disk, self.path.read_bytes())

    async def test_unlocked_elimination_requires_lock_without_mutation(self):
        for multiplier in (1, 5):
            for remove, last in ((True, False), (False, True), (True, True)):
                with self.subTest(multiplier=multiplier, remove=remove, last=last):
                    self.state.set_multiplier(multiplier)
                    self.state.set_remove_on_win(remove)
                    self.state.set_last_man_standing(last)
                    before = copy.deepcopy(self.state.__dict__)
                    disk = self.path.read_bytes()
                    with patch('bot.wheel_state.random.randrange') as draw:
                        with self.assertRaisesRegex(WheelOperationError, '!wheellock on'):
                            self.state.spin()
                        with self.assertLogs(level='ERROR'):
                            ctx, broadcast = await self.command('wheel_spin', '!wheelspin')
                        draw.assert_not_called()
                    self.assertIn('!wheellock on', ctx.send.call_args.args[0])
                    broadcast.assert_not_awaited()
                    self.assertEqual(before, self.state.__dict__)
                    self.assertEqual(disk, self.path.read_bytes())
                    self.assert_unlocked_counts()

    def assert_unlocked_counts(self):
        self.assertFalse(self.state.wheel_locked)
        self.assertTrue(all(count == self.state.multiplier for count in self.state.slots.values()))
        self.assertEqual(self.state.slots, self.persisted()['slots'])

    async def test_every_successful_unlocked_operation_preserves_universal_counts(self):
        self.state.set_multiplier(5)
        operations = [lambda: self.state.join('bob'),
                      lambda: self.state.add_slots('extra', 9, manual=True),
                      lambda: self.state.remove_user('bob'),
                      lambda: self.state.set_color('alice', '#abcdef'),
                      lambda: self.state.set_multiplier(3),
                      lambda: self.state.set_all_counts(4),
                      lambda: self.state.set_remove_on_win(True),
                      lambda: self.state.set_last_man_standing(True),
                      lambda: self.state.set_wheel_locked(False),
                      lambda: self.state.set_remove_on_win(False),
                      lambda: self.state.set_last_man_standing(False),
                      self.state.spin, self.state.load, self.state.reset]
        for operation in operations:
            operation()
            self.assert_unlocked_counts()

    async def test_ordinary_unlocked_spin_preserves_configured_counts(self):
        self.state.set_multiplier(5)
        with patch('bot.wheel_state.random.randrange', return_value=0), patch.object(wheel_cog.asyncio, 'sleep', new_callable=AsyncMock):
            _, broadcast = await self.command('wheel_spin', '!wheelspin')
        self.assertEqual(2, broadcast.await_count)
        self.assertEqual(1, self.state.scores['alice'])
        self.assert_unlocked_counts()
        self.state.reset()
        self.assertEqual((None, None, None), self.state.spin())
        self.assert_unlocked_counts()

    async def test_locked_elimination_modes_decrement_remove_and_unlock(self):
        for remove, last in ((True, False), (False, True), (True, True)):
            self.state.reset()
            self.state.set_multiplier(2)
            self.state.join('alice')
            self.state.add_slots('manual', manual=True)
            self.state.set_remove_on_win(remove)
            self.state.set_last_man_standing(last)
            self.state.set_wheel_locked(True)
            with patch('bot.wheel_state.random.randrange', return_value=0):
                self.state.spin()
                self.assertEqual({'alice': 1, 'manual': 2}, self.state.slots)
                self.state.spin()
                self.assertNotIn('alice', self.state.order)
                self.state.spin()
                self.assertEqual({'manual': 1}, self.state.slots)
            before = copy.deepcopy(self.state.__dict__)
            original = __import__('os').replace
            def replace(source, target):
                self.assertEqual(before, self.state.__dict__)
                self.assertEqual({'manual': 2}, json.loads(Path(source).read_text())['slots'])
                original(source, target)
            with patch('bot.wheel_state.os.replace', side_effect=replace):
                _, broadcast = await self.command('wheel_lock', '!wheellock off')
            broadcast.assert_awaited_once_with(self.state.get_state_payload())
            self.assertEqual({'manual'}, self.state.manual_users)
            self.assert_unlocked_counts()

    def write_legacy(self):
        data = self.persisted()
        data.update(multiplier=5, wheel_locked=False, slots={'alice': 1, 'manual': 7}, extra={'keep': True})
        self.path.write_text(json.dumps(data))

    async def test_legacy_load_reload_payload_and_noop_reconcile_before_publication(self):
        for route in ('constructor', 'load', 'payload', 'noop'):
            with self.subTest(route=route):
                self.write_legacy()
                before = copy.deepcopy(self.state.__dict__)
                original = __import__('os').replace
                def replace(source, target):
                    self.assertEqual(before, self.state.__dict__)
                    self.assertEqual({'alice': 5, 'manual': 5}, json.loads(Path(source).read_text())['slots'])
                    original(source, target)
                with patch('bot.wheel_state.os.replace', side_effect=replace) as save:
                    if route == 'constructor':
                        loaded = WheelState(self.path)
                        self.assertEqual({'alice': 5, 'manual': 5}, loaded.slots)
                    elif route == 'load':
                        self.state.load()
                    elif route == 'payload':
                        with patch.object(overlay_server, 'WHEEL_STATE_FILE', str(self.path)):
                            payload = overlay_server._wheel_payload_from_file()
                        self.assertEqual({5}, {s['count'] for s in payload['slots']})
                    else:
                        self.assertFalse(self.state.join('alice'))
                    save.assert_called_once()
                self.state.load()
                self.assert_unlocked_counts()
                self.assertEqual({'keep': True}, self.persisted()['extra'])
                self.assertEqual({'manual'}, self.state.manual_users)

    async def test_legacy_reconciliation_failure_preserves_live_disk_and_registry(self):
        from bot import wheel_state
        self.write_legacy()
        before = copy.deepcopy(self.state.__dict__)
        slots = self.state.slots
        disk = self.path.read_bytes()
        for failure in ('json.dump', 'os.replace'):
            with patch('bot.wheel_state.' + failure, side_effect=OSError('disk')):
                for operation in (self.state.load, lambda: WheelState(self.path), lambda: self.state.join('alice')):
                    with self.assertRaises(WheelOperationError):
                        operation()
                with patch.object(wheel_state, '_states', {}):
                    with self.assertRaises(WheelOperationError):
                        get_wheel_state(self.path)
                    self.assertEqual({}, wheel_state._states)
                with self.assertLogs(level='ERROR'):
                    _, broadcast = await self.command('wheel_color', '!wheelcolor #abcdef')
                broadcast.assert_not_awaited()
                with self.assertLogs(level='ERROR'):
                    broadcast = await self.websocket('set_remove_on_win', True)
                broadcast.assert_not_awaited()
            self.assertIs(slots, self.state.slots)
            self.assertEqual(before, self.state.__dict__)
            self.assertEqual(disk, self.path.read_bytes())
            self.assertEqual([self.path], list(self.path.parent.iterdir()))

    async def test_legacy_refresh_validation_failure_does_not_commit_reconciliation(self):
        self.write_legacy()
        before = copy.deepcopy(self.state.__dict__)
        disk = self.path.read_bytes()
        with self.assertRaises(WheelOperationError):
            self.state.set_multiplier(0)
        self.assertEqual(before, self.state.__dict__)
        self.assertEqual(disk, self.path.read_bytes())
