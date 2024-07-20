"""
All the enums for commands
"""

from enum import Enum


# pylint: disable=missing-class-docstring invalid-name
class Connections(Enum):
    welcome = b"WELCOME"
    heartbeat = b"Heartbeat\r\n"
    bye = b"Bye\r\n"


class Footer(Enum):
    footer = b"\x0D\x0A"


class Headers(Enum):
    temperature = b"Temperatures"
    activate_profile = b"ActivateProfile"
    incoming_signal = b"IncomingSignalInfo"
    outgoing_signal = b"OngoingSignalInfo"
    aspect_ratio = b"AspectRatio"
    masking_ratio = b"MaskingRatio"
    mac = b"MacAddress"
    setting_page = b"SettingPage"
    config_page = b"ConfigPage"
    option = b"Option"


class ACKs(Enum):
    reply = b"OK\r\n"
    error = b"ERROR"


class Temperatures(Enum):
    msg = "Temperatures"


class SignalInfo(Enum):
    msg = "IncomingSignalInfo"


class OutgoingSignalInfo(Enum):
    msg = "OutgoingSignalInfo"


class AspectRatio(Enum):
    msg = "AspectRatio"


class Notifications(Enum):
    ActivateProfile = b"ActivateProfile"
    IncomingSignalInfo = b"IncomingSignalInfo"
    OngoingSignalInfo = b"OngoingSignalInfo"
    AspectRatio = b"AspectRatio"
    MaskingRatio = b"MaskingRatio"


class KeyPress(Enum):
    MENU = b"MENU"
    UP = b"UP"
    DOWN = b"DOWN"
    LEFT = b"LEFT"
    RIGHT = b"RIGHT"
    OK = b"OK"
    INPUT = b"INPUT"
    SETTINGS = b"SETTINGS"
    RED = b"RED"
    GREEN = b"GREEN"
    BLUE = b"BLUE"
    YELLOW = b"YELLOW"
    POWER = b"POWER"


class DisplayAlert(Enum):
    pass


class Information(Enum):
    pass


class SettingsPages(Enum):
    pass


class Toggle(Enum):
    ToneMap = b"ToneMap"
    HighlightRecovery = b"HighlightRecovery"
    ContrastRecovery = b"ContrastRecovery"
    ShadowRecovery = b"ShadowRecovery"
    _3DLUT = b"3DLUT"
    ScreenBoundaries = b"ScreenBoundaries"
    Histogram = b"Histogram"
    DebugOSD = b"DebugOSD"


class SingleCmd(Enum):
    """for things that are single words"""


class IsInformational(Enum):
    true = True
    false = False


class Menus(Enum):
    Info = b"Info"
    Settings = b"Settings"
    Configuration = b"Configuration"
    Profiles = b"Profiles"
    TestPatterns = b"TestPatterns"


class Profiles(Enum):
    SOURCE = b"SOURCE"
    DISPLAY = b"DISPLAY"
    # CUSTOM 2
    CUSTOM = b"CUSTOM"


class Commands(Enum):
    # Power stuff
    PowerOff = b"PowerOff", SingleCmd, IsInformational.false
    Standby = b"Standby", SingleCmd, IsInformational.false
    Restart = b"Restart", SingleCmd, IsInformational.false
    ReloadSoftware = b"ReloadSoftware", SingleCmd, IsInformational.false
    Bye = b"Bye", SingleCmd, IsInformational.false
    ResetTemporary = b"ResetTemporary", SingleCmd, IsInformational.false

    ActivateProfile = b"ActivateProfile", Profiles, IsInformational.false

    # Menu
    OpenMenu = b"OpenMenu", Menus, IsInformational.false
    CloseMenu = b"CloseMenu", SingleCmd, IsInformational.false
    KeyPress = b"KeyPress", KeyPress, IsInformational.false
    KeyHold = b"KeyHold", KeyPress, IsInformational.false

    GetIncomingSignalInfo = b"GetIncomingSignalInfo", SignalInfo, IsInformational.true
    GetOutgoingSignalInfo = (
        b"GetOutgoingSignalInfo",
        OutgoingSignalInfo,
        IsInformational.true,
    )
    GetAspectRatio = b"GetAspectRatio", AspectRatio, IsInformational.true
    GetMaskingRatio = b"GetMaskingRatio", SingleCmd, IsInformational.true
    GetTemperatures = b"GetTemperatures", Temperatures, IsInformational.true
    GetMacAddress = b"GetMacAddress", SingleCmd, IsInformational.true

    Toggle = b"Toggle", Toggle, IsInformational.false
    ToneMapOn = b"ToneMapOn", SingleCmd, IsInformational.false
    ToneMapOff = b"ToneMapOff", SingleCmd, IsInformational.false

    Hotplug = b"Hotplug", SingleCmd, IsInformational.false
    RefreshLicenseInfo = b"RefreshLicenseInfo", SingleCmd, IsInformational.false
    Force1080p60Output = b"Force1080p60Output", SingleCmd, IsInformational.false
