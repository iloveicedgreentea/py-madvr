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
    footer = b"\x0d\x0a"


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


class AspectRatioMode(Enum):
    Auto = b"Auto"
    Hold = b"Hold"
    _4_3 = b"4:3"
    _16_9 = b"16:9"
    _1_85_1 = b"1.85:1"
    _2_00_1 = b"2.00:1"
    _2_20_1 = b"2.20:1"
    _2_35_1 = b"2.35:1"
    _2_40_1 = b"2.40:1"
    _2_55_1 = b"2.55:1"
    _2_76_1 = b"2.76:1"


class DisplayAlert(Enum):
    pass


class DisplayMessage(Enum):
    """For DisplayMessage command parameters"""

    pass


class DisplayAudioVolume(Enum):
    """For DisplayAudioVolume command parameters"""

    pass


class Information(Enum):
    pass


class Parameters(Enum):
    """Marker for commands accepting protocol-defined free-form parameters."""

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
    DisplayAlertWindow = b"DisplayAlertWindow", Parameters, IsInformational.false
    CloseAlertWindow = b"CloseAlertWindow", SingleCmd, IsInformational.false
    SetAspectRatioMode = b"SetAspectRatioMode", AspectRatioMode, IsInformational.false

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

    # Profiles and options
    CreateProfileGroup = b"CreateProfileGroup", Parameters, IsInformational.false
    RenameProfileGroup = b"RenameProfileGroup", Parameters, IsInformational.false
    EnumProfileGroups = b"EnumProfileGroups", SingleCmd, IsInformational.true
    CreateProfile = b"CreateProfile", Parameters, IsInformational.false
    RenameProfile = b"RenameProfile", Parameters, IsInformational.false
    AddProfileToPage = b"AddProfileToPage", Parameters, IsInformational.false
    RemoveProfileFromPage = b"RemoveProfileFromPage", Parameters, IsInformational.false
    GetActiveProfile = b"GetActiveProfile", Parameters, IsInformational.true
    EnumProfiles = b"EnumProfiles", Parameters, IsInformational.true

    EnumSettingPages = b"EnumSettingPages", SingleCmd, IsInformational.true
    EnumConfigPages = b"EnumConfigPages", SingleCmd, IsInformational.true
    EnumOptions = b"EnumOptions", Parameters, IsInformational.true
    QueryOption = b"QueryOption", Parameters, IsInformational.true
    ChangeOption = b"ChangeOption", Parameters, IsInformational.false
    InheritOption = b"InheritOption", Parameters, IsInformational.false

    Toggle = b"Toggle", Toggle, IsInformational.false
    ToneMapOn = b"ToneMapOn", SingleCmd, IsInformational.false
    ToneMapOff = b"ToneMapOff", SingleCmd, IsInformational.false

    Hotplug = b"Hotplug", SingleCmd, IsInformational.false
    RefreshLicenseInfo = b"RefreshLicenseInfo", SingleCmd, IsInformational.false
    Force1080p60Output = b"Force1080p60Output", SingleCmd, IsInformational.false

    # Display commands
    DisplayMessage = b"DisplayMessage", DisplayMessage, IsInformational.false
    DisplayAudioVolume = b"DisplayAudioVolume", DisplayAudioVolume, IsInformational.false
    DisplayAudioMute = b"DisplayAudioMute", SingleCmd, IsInformational.false
    CloseAudioMute = b"CloseAudioMute", SingleCmd, IsInformational.false
