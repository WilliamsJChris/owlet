"""Test Owlet switches."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from . import async_init_integration


async def test_recovery_mode_switch(hass: HomeAssistant) -> None:
    """Test recovery mode state and commands."""
    await async_init_integration(hass)

    state = next(
        state
        for state in hass.states.async_all("switch")
        if state.attributes.get("friendly_name", "").endswith("Recovery Mode")
    )
    entity_id = state.entity_id
    assert state.state == "off"

    coordinator = next(iter(hass.data["owlet"].values()))
    coordinator.sock.raw_properties["APP_CMD_RESPONSE"]["value"] = (
        '{"cmd":"mon_recovery","val":"true"}'
    )
    coordinator.async_set_updated_data(coordinator.data)
    await hass.async_block_till_done()

    assert hass.states[entity_id].state == "on"

    post_command = AsyncMock(return_value={})
    with patch.object(coordinator.sock._api, "post_command", post_command), patch.object(
        coordinator, "async_request_refresh", AsyncMock()
    ) as refresh:
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )

    post_command.assert_awaited_once_with(
        coordinator.sock.serial,
        "APP_CMD_REQUEST",
        {
            "datapoint": {
                "metadata": {},
                "value": '{"cmd":"mon_recovery","val":"false"}',
            }
        },
    )
    refresh.assert_awaited_once()