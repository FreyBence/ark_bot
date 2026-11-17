import ast
import asyncio
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import discord
from steam_progress import SteamProgress


class MessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_message_refreshed_and_completed(self):
        message = SimpleNamespace(edit=AsyncMock())
        ctx = SimpleNamespace(send=AsyncMock(return_value=message))
        async def fast_sleep(delay):
            self.assertEqual(delay, 5)
            await asyncio.sleep(0)
        proxy = SimpleNamespace(sleep=fast_sleep, create_task=asyncio.create_task,
                                CancelledError=asyncio.CancelledError)
        tree = ast.parse(Path("dc_bot.py").read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)
                  and n.name == "_run_with_progress")
        ns = dict(asyncio=proxy, time=time, SteamProgress=SteamProgress, discord=discord)
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "dc_bot.py", "exec"), ns)
        async def operation(progress):
            progress.feed("Update state (0x61) downloading, progress: 42.0\n")
            for _ in range(5):
                await asyncio.sleep(0)
            return True, "Server initialized."
        await ns["_run_with_progress"](ctx, operation, "Initializing ARK server")
        ctx.send.assert_awaited_once()
        updates = [call.kwargs["content"] for call in message.edit.await_args_list]
        self.assertTrue(any("42.0%" in content for content in updates))
        self.assertIn("Completed", updates[-1])
        count = len(updates)
        await asyncio.sleep(0)
        self.assertEqual(message.edit.await_count, count)


if __name__ == "__main__":
    unittest.main()
