import asyncio
import contextlib
import dataclasses
import pkgutil
from typing import TypedDict, cast

import dotenv

import discord
import hot


@dataclasses.dataclass
class Env:
    TOKEN: str


class EnvType(TypedDict):
    TOKEN: str


class Bot(hot.HMR):
    def test(self):
        return "a"

    async def setup_hook(self):
        for module in pkgutil.iter_modules(["src/cogs"], prefix="src.cogs."):
            print("Loading", module.name)

            await self.load_extension(module.name)

        if self.user is not None:
            print(self.user.name, "is up!")


async def main():
    unparsed_env = cast(EnvType, dotenv.dotenv_values())
    env = Env(**unparsed_env)
    bot = Bot(intents=discord.Intents.all(), command_prefix="bingus ")

    async with bot:
        await bot.start(env.TOKEN)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt, RuntimeError, asyncio.CancelledError):
        asyncio.run(main())
