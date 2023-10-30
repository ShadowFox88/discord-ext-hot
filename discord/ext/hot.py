from __future__ import annotations

import asyncio
import dataclasses
import importlib
import importlib.util
import os
import traceback
from typing import Any, Callable, Coroutine

import watchfiles

from discord.ext import commands

__all__ = ("HMR",)

CWD = os.getcwd()


@dataclasses.dataclass
class Environment:
    RELATIVE_EXTENSIONS_PATH: str


ENV = Environment(
    RELATIVE_EXTENSIONS_PATH=os.getenv("RELATIVE_EXTENSIONS_PATH", "src/cogs/"),
)


def path_to_mod(filepath: str) -> str:
    resolved_filepath = os.path.abspath(filepath)
    accurate_relative_filepath = os.path.relpath(resolved_filepath, start=CWD)

    if filepath.startswith("/"):
        filepath = filepath[1:]
    elif filepath.startswith("./"):
        filepath = filepath[2:]

    return accurate_relative_filepath.replace("/", ".").replace(".py", "")


class HMR(commands.Bot):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        self.loop = asyncio.get_event_loop()
        self.__internal_task: asyncio.Task[None] = self.loop.create_task(self.__watch_files())

    async def _default_file_added_handler(self, name: str):
        module_path = path_to_mod(name)
        spec = importlib.util.find_spec(module_path)

        assert spec is not None, "spec retrieval failed"

        module = importlib.util.module_from_spec(spec)

        if _is_extension := hasattr(module, "setup"):
            await self.load_extension(module_path)

        self.dispatch("file_added", module_path, module)

    async def _default_file_modified_handler(self, name: str):
        module_path = path_to_mod(name)
        # in the case where a file is cleared/modified, we have to check if the
        # entry point remains, as drastic change may lead to empty files/creating non-cogs
        spec = importlib.util.find_spec(module_path)

        assert spec is not None, "spec retrieval failed"

        module = importlib.util.module_from_spec(spec)

        if _is_extension := hasattr(module, "setup"):
            try:
                await self.reload_extension(module_path)
            except commands.ExtensionNotLoaded:
                await self.load_extension(module_path)

        self.dispatch("file_modified", module_path, module)

    async def _default_file_deleted_handler(self, name: str):
        module_path = path_to_mod(name)

        try:
            await self.unload_extension(module_path)
        except commands.ExtensionNotLoaded:
            pass

        self.dispatch("file_deleted", module_path)

    async def _maybe_call_file_handler(
        self, filepath: str, type: str, default: Callable[[str], Coroutine[None, None, None]]
    ):
        name = f"on_file_{type}"

        try:
            # sourcery skip: use-named-expression
            file_handler_found: Callable[[str], Coroutine[None, None, None]] | None = getattr(self, name, None)

            if file_handler_found:
                return await file_handler_found(filepath)

            await default(filepath)
        except Exception as error:
            if error_handler_found := getattr(self, "on_error", None):
                await error_handler_found(error)

            traceback.print_exception(error.__class__, error, error.__traceback__)

    async def _process_file_manipulation(self, change_type: watchfiles.Change, filepath: str):
        if not filepath.endswith(".py"):
            return

        type_ = change_type.name

        match change_type:
            case watchfiles.Change.added:
                await self._maybe_call_file_handler(filepath, type_, default=self._default_file_added_handler)
            case watchfiles.Change.modified:
                await self._maybe_call_file_handler(filepath, type_, default=self._default_file_modified_handler)
            case watchfiles.Change.deleted:
                await self._maybe_call_file_handler(filepath, type_, default=self._default_file_deleted_handler)

    async def __watch_files(self):
        async for changes in watchfiles.awatch("./"):  # type: ignore - watchfiles has no type stubs for this
            for change_type, filepath in changes:
                await self._process_file_manipulation(change_type, filepath)

    async def close(self):
        try:
            self.__internal_task.cancel()
        except asyncio.CancelledError:
            pass
