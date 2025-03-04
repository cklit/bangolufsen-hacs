"""Select entities for the Bang & Olufsen Mozart integration."""
from __future__ import annotations

import logging
from multiprocessing.pool import ApplyResult
from typing import cast

from mozart_api.models import (
    ListeningMode,
    ListeningModeProps,
    ListeningModeRef,
    Scene,
    SpeakerGroupOverview,
)

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ENTITY_ENUM, WEBSOCKET_NOTIFICATION
from .entity import BangOlufsenEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Select entities from config entry."""
    entities = []

    # Add Select entities.
    for select in hass.data[DOMAIN][config_entry.unique_id][ENTITY_ENUM.SELECTS]:
        entities.append(select)

    async_add_entities(new_entities=entities)


class BangOlufsenSelect(BangOlufsenEntity, SelectEntity):
    """Select for Mozart settings."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ConfigEntry) -> None:
        """Init the Select."""
        super().__init__(entry)

        self._attr_current_option = None
        self._attr_options = []


class BangOlufsenSelectSoundMode(BangOlufsenSelect):
    """Sound mode Select."""

    _attr_icon = "mdi:sine-wave"
    _attr_translation_key = "sound_mode"

    def __init__(self, entry: ConfigEntry) -> None:
        """Init the sound mode select."""
        super().__init__(entry)

        self._attr_unique_id = f"{self._unique_id}-sound-mode"

        self._sound_modes: dict[str, int] = {}

    async def async_added_to_hass(self) -> None:
        """Turn on the dispatchers."""
        await super().async_added_to_hass()

        self._dispatchers.append(
            async_dispatcher_connect(
                self.hass,
                f"{self._unique_id}_{WEBSOCKET_NOTIFICATION.ACTIVE_LISTENING_MODE}",
                self._update_sound_modes,
            )
        )

        await self._update_sound_modes()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        self._client.activate_listening_mode(
            id=self._sound_modes[option], async_req=True
        )

    async def _update_sound_modes(
        self, active_sound_mode: ListeningModeProps | ListeningModeRef | None = None
    ) -> None:
        """Get the available sound modes and setup Select functionality."""
        sound_modes = cast(
            ApplyResult[list[ListeningMode]],
            self._client.get_listening_mode_set(async_req=True),
        ).get()
        if active_sound_mode is None:
            active_sound_mode = cast(
                ApplyResult[ListeningModeRef],
                self._client.get_active_listening_mode(async_req=True),
            ).get()

        # Add the key to make the labels unique as well
        for sound_mode in sound_modes:
            label = f"{sound_mode.name} - {sound_mode.id}"

            self._sound_modes[label] = sound_mode.id

            if sound_mode.id == active_sound_mode.id:
                self._attr_current_option = label

        # Set available options and selected option.
        self._attr_options = list(self._sound_modes.keys())

        self.async_write_ha_state()


class BangOlufsenSelectListeningPosition(BangOlufsenSelect):
    """Listening position Select."""

    _attr_icon = "mdi:sine-wave"
    _attr_translation_key = "listening_position"

    def __init__(self, entry: ConfigEntry) -> None:
        """Init the listening position select."""
        super().__init__(entry)

        self._attr_unique_id = f"{self._unique_id}-listening-position"

        self._listening_positions: dict[str, str] = {}
        self._scenes: dict[str, str] = {}

    async def async_added_to_hass(self) -> None:
        """Turn on the dispatchers."""
        await super().async_added_to_hass()

        self._dispatchers.extend(
            [
                async_dispatcher_connect(
                    self.hass,
                    f"{self._unique_id}_{WEBSOCKET_NOTIFICATION.ACTIVE_SPEAKER_GROUP}",
                    self._update_listening_positions,
                ),
                async_dispatcher_connect(
                    self.hass,
                    f"{self._unique_id}_{WEBSOCKET_NOTIFICATION.REMOTE_MENU_CHANGED}",
                    self._update_listening_positions,
                ),
            ]
        )

        await self._update_listening_positions()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        self._client.post_scene_trigger(
            id=self._listening_positions[option], async_req=True
        )

    async def _update_listening_positions(
        self, active_speaker_group: SpeakerGroupOverview | None = None
    ) -> None:
        """Update listening position."""
        scenes = cast(
            ApplyResult[dict[str, Scene]], self._client.get_all_scenes(async_req=True)
        ).get()

        if active_speaker_group is None:
            active_speaker_group = cast(
                ApplyResult[SpeakerGroupOverview],
                self._client.get_speakergroup_active(async_req=True),
            ).get()

        self._listening_positions = {}

        # Listening positions
        for scene_key in scenes:
            scene = scenes[scene_key]

            if (
                scene.tags is not None
                and "listeningposition" in scene.tags
                and scene.label is not None
            ):
                # Ignore listening positions with the same name
                if scene.label is not None:
                    if scene.label in self._listening_positions:
                        _LOGGER.warning(
                            "Ignoring listening position with duplicate name: %s and ID: %s",
                            scene.label,
                            scene_key,
                        )
                        continue

                    self._listening_positions[scene.label] = scene_key

                # Currently guess the current active listening position by the speakergroup ID
                if active_speaker_group.id == scene.action_list[0].speaker_group_id:
                    self._attr_current_option = scene.label

        self._attr_options = list(self._listening_positions.keys())

        self.async_write_ha_state()
