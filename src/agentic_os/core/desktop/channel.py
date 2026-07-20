"""Channel Manager — manages update channels (stable, beta, nightly)."""

from __future__ import annotations

from collections.abc import Sequence

from agentic_os.domain.desktop import UpdateChannel
from agentic_os.infrastructure.logging import get_logger

log = get_logger("desktop.channel")


class ChannelManager:
    """Manages update release channels."""

    def __init__(self) -> None:
        self._current_channel = UpdateChannel.STABLE
        self._available_channels = [UpdateChannel.STABLE, UpdateChannel.BETA, UpdateChannel.NIGHTLY]

    async def get_channels(self) -> Sequence[UpdateChannel]:
        return self._available_channels

    async def set_channel(self, channel: UpdateChannel) -> None:
        self._current_channel = channel
        log.info("Update channel changed", channel=channel.value)

    async def get_current_channel(self) -> UpdateChannel:
        return self._current_channel
