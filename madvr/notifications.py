"""Implement notification processing for MadVR."""

import logging


class NotificationProcessor:
    """Process notifications from MadVR."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.msg_dict: dict = {}

    async def process_notifications(self, msg: str) -> dict:
        """Parse a message and store the attributes and values in a dictionary"""
        self.logger.debug("Processing notifications: %s", msg)
        notifications = msg.strip().split("\r\n")

        for notification in notifications:
            # ignore ok
            if not notification or notification == "OK":
                continue

            parts = notification.split(" ", 1)
            # ignore empty notifications
            if len(parts) < 2:
                continue

            title, signal_info = parts
            self.logger.debug("Processing notification Title: %s", title)

            if title == "PowerOff":
                self.msg_dict["is_on"] = False
            elif title == "NoSignal":
                self.msg_dict["is_signal"] = False
            elif title == "Standby":
                self.msg_dict["is_on"] = False
            else:
                self._process_signal_info(title, signal_info.split())

        return self.msg_dict

    def _process_signal_info(self, title: str, signal_info: list[str]) -> None:
        processors = {
            "IncomingSignalInfo": self._process_incoming_signal,
            "OutgoingSignalInfo": self._process_outgoing_signal,
            "AspectRatio": self._process_aspect_ratio,
            "MaskingRatio": self._process_masking_ratio,
            "ActivateProfile": self._process_profile,
            "ActiveProfile": self._process_profile,
            "MacAddress": self._process_mac_address,
            "Temperatures": self._process_temperatures,
        }
        processor = processors.get(title)
        if processor:
            try:
                # Call the processor function
                processor(signal_info)
            except (KeyError, IndexError) as e:
                self.logger.error(f"Error processing {title}: {e}")
                self.logger.debug(f"Signal info: {signal_info}")

    def _process_mac_address(self, info: list[str]) -> None:
        self.msg_dict["mac_address"] = info[0]

    def _process_temperatures(self, info: list[str]) -> None:
        self.msg_dict.update(
            {
                "temp_gpu": info[0],
                "temp_hdmi": info[1],
                "temp_cpu": info[2],
                "temp_mainboard": info[3],
            }
        )

    def _process_incoming_signal(self, info: list[str]) -> None:
        self.msg_dict.update(
            {
                "is_signal": True,
                "incoming_res": info[0],
                "incoming_frame_rate": info[1],
                # 2D || 3D
                "incoming_signal_type": info[2],
                "incoming_color_space": info[3],
                "incoming_bit_depth": info[4],
                "hdr_flag": "HDR" in info[5],
                "incoming_colorimetry": info[6],
                "incoming_black_levels": info[7],
                "incoming_aspect_ratio": info[8],
            }
        )

    def _process_outgoing_signal(self, info: list[str]) -> None:
        self.msg_dict.update(
            {
                "outgoing_res": info[0],
                "outgoing_frame_rate": info[1],
                "outgoing_signal_type": info[2],  # 2D || 3D
                "outgoing_color_space": info[3],
                "outgoing_bit_depth": info[4],
                "outgoing_hdr_flag": "HDR" in info[5],
                "outgoing_colorimetry": info[6],
                "outgoing_black_levels": info[7],
            }
        )

    def _process_aspect_ratio(self, info: list[str]) -> None:
        self.msg_dict.update(
            {
                "aspect_res": info[0],
                "aspect_dec": float(info[1]),
                "aspect_int": info[2],
                "aspect_name": info[3],
            }
        )

    def _process_masking_ratio(self, info: list[str]) -> None:
        self.msg_dict.update(
            {
                "masking_res": info[0],
                "masking_dec": float(info[1]),
                "masking_int": info[2],
            }
        )

    def _process_profile(self, info: list[str]) -> None:
        self.msg_dict.update(
            {
                "profile_name": info[0],
                "profile_num": info[1],
            }
        )
