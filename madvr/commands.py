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
    incoming_signal_info = b"IncomingSignalInfo"
    outgoing_signal_info = b"OngoingSignalInfo"
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
    pass

class Notifications(Enum):
    activate_profile = b"ActivateProfile"
    incoming_signal = b"IncomingSignalInfo"
    outgoing_signal = b"OngoingSignalInfo"
    aspect_ratio = b"AspectRatio"
    masking_ratio = b"MaskingRatio"

class KeyPress(Enum):
    menu = b"MENU"
    up = b"UP"
    down = b"DOWN"
    left = b"LEFT"
    right = b"RIGHT"
    ok = b"OK"
    inp = b"INPUT"
    settings = b"SETTINGS"
    red = b"RED"
    green = b"GREEN"
    blue = b"BLUE"
    yellow = b"YELLOW"
    power = b"POWER"

class DisplayAlert(Enum):
    pass

class Information(Enum):
    pass

class Profiles(Enum):
    pass

class SettingsPages(Enum):
    pass

class Toggle(Enum):
    pass

class SingleCmd(Enum):
    """for things that are single words"""
    pass

class IsInformational(Enum):
    true = True
    false = False

class Commands(Enum):
    # Power stuff
    power_off = b"PowerOff", SingleCmd, IsInformational.false
    standby = b"Standby", SingleCmd, IsInformational.false
    restart = b"Restart", SingleCmd, IsInformational.false
    reload_software = b"ReloadSoftware", SingleCmd, IsInformational.false
    bye = b"Bye", SingleCmd, IsInformational.false

    #  vb'KeyPress MENU\r\n'
# b'CloseMenu\r\n'
# b'OK\r\nIncomingSignalInfo 3840x2160 59.940p 2D 420 10bit SDR 709 TV 16:9\r\nReloadSoftware\r\nOutgoingSignalInfo 4096x2160 59.940p 2D RGB 8bit SDR 709 TV\r\nIncomingSignalInfo 3840x2160 59.940p 2D 420 10bit SDR 709 TV 16:9\r\nAspectRatio 3840:2160 1.778 178 "16:9"\r\nMaskingRatio 3044:1712 1.778 178\r\nKeyPress MENU\r\nOpenMenu Configuration\r\n'
    # playing fast n furous 
    # b'OK\r\nAspectRatio 3816:2146 1.778 178 "16:9"\r\nResetTemporary\r\nNoSignal\r\nOutgoingSignalInfo 4096x2160 59.940p 2D RGB 8bit SDR 709 TV\r\nIncomingSignalInfo 1280x720 59.940p 2D 422 12bit SDR 709 TV 16:9\r\nAspectRatio 1280:0720 1.778 178 "16:9"\r\nAspectRatio 1272:0525 2.423 240 "Panavision"\r\nMaskingRatio 4092:1689 2.423 240\r\n'

    # Menu
    open_menu = b"OpenMenu", SingleCmd, IsInformational.false
    close_menu = b"CloseMenu", SingleCmd, IsInformational.false
    key_press = b"KeyPress", KeyPress, IsInformational.false
    key_press_hold = b"KeyHold", KeyPress, IsInformational.false
    

    # display_alert = b"DisplayAlertWindow", ACKs.reply
    # close_alert = b"CloseAlertWindow", ACKs.reply
    # display_message = b"DisplayMessage", ACKs.reply

    get_signal_info = b"GetIncomingSignalInfo", SingleCmd, IsInformational.true
    get_aspect_ratio = b"GetAspectRatio", SingleCmd, IsInformational.true
    get_masking_ratio = b"GetMaskingRatio", SingleCmd, IsInformational.true
    get_temp = b"GetTemperatures", SingleCmd, IsInformational.true
    get_mac = b"GetMacAddress", SingleCmd, IsInformational.true

    # enum_settings = b"EnumSettingsPages"
    # enum_configs = b"EnumConfigPages"
    # enum_options = b"EnumOptions"
    # query_option = b"QueryOption"
    # change_option = b"ChangeOption"
    # reset_temp = b"ResetTemporary"

    # toggle = b"Toggle"
    tone_map_on = b"ToneMapOn", SingleCmd, IsInformational.false
    tone_map_off = b"ToneMapOff", SingleCmd, IsInformational.false

    hotplug = b"Hotplug", SingleCmd, IsInformational.false
    refresh_license = b"RefreshLicenseInfo", SingleCmd, IsInformational.false
    force_1080p = b"Force1080p60Output", SingleCmd, IsInformational.false
