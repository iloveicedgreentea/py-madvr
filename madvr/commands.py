"""
All the enums for commands
"""
from enum import Enum


# pylint: disable=missing-class-docstring invalid-name
class Connections(Enum):
    welcome = b"WELCOME"
    heartbeat = b"Heartbeat\r"
    bye = b"Bye\r\n"

class Footer(Enum):
    footer = b" \x0D \x0A"

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
   

class Notifications(Enum):
    pass

class PowerCommands(Enum):
    pass

class MenuCommands(Enum):
    pass

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

class Other(Enum):
    pass


class Commands(Enum):
    # Notifications
    activate_profile = b"ActivateProfile"
    incoming_signal = b"IncomingSignalInfo"
    outgoing_signal = b"OngoingSignalInfo"
    aspect_ratio = b"AspectRatio"
    masking_ratio = b"MaskingRatio"

    # Power stuff
    power_off = b"PowerOff", ACKs.reply
    standby = b"Standby", ACKs.reply
    restart = b"Restart", ACKs.reply
    reload_software = b"ReloadSoftware", ACKs.reply
    bye = b"Bye", ACKs.reply
    #  vb'KeyPress MENU\r\n'
# b'CloseMenu\r\n'
# b'OK\r\nIncomingSignalInfo 3840x2160 59.940p 2D 420 10bit SDR 709 TV 16:9\r\nReloadSoftware\r\nOutgoingSignalInfo 4096x2160 59.940p 2D RGB 8bit SDR 709 TV\r\nIncomingSignalInfo 3840x2160 59.940p 2D 420 10bit SDR 709 TV 16:9\r\nAspectRatio 3840:2160 1.778 178 "16:9"\r\nMaskingRatio 3044:1712 1.778 178\r\nKeyPress MENU\r\nOpenMenu Configuration\r\n'
    # playing fast n furous 
    # b'OK\r\nAspectRatio 3816:2146 1.778 178 "16:9"\r\nResetTemporary\r\nNoSignal\r\nOutgoingSignalInfo 4096x2160 59.940p 2D RGB 8bit SDR 709 TV\r\nIncomingSignalInfo 1280x720 59.940p 2D 422 12bit SDR 709 TV 16:9\r\nAspectRatio 1280:0720 1.778 178 "16:9"\r\nAspectRatio 1272:0525 2.423 240 "Panavision"\r\nMaskingRatio 4092:1689 2.423 240\r\n'

    # Menu
    open_menu = b"OpenMenu", ACKs.reply
    close_menu = b"CloseMenu", ACKs.reply
    key_press = b"KeyPress", ACKs.reply
    key_press_hold = b"KeyHold", ACKs.reply
    # "POWER, MENU, LEFT, RIGHT, UP, DOWN, OK, INPUT, SETTINGS, RED, GREEN, BLUE, YELLOW"

    display_alert = b"DisplayAlertWindow", ACKs.reply
    close_alert = b"CloseAlertWindow", ACKs.reply
    display_message = b"DisplayMessage", ACKs.reply

    get_signal_info = b"GetIncomingSignalInfo"
    get_aspect_ratio = b"GetAspectRatio"
    get_masking_ratio = b"GetMaskingRatio"
    get_temp = b"GetTemperatures"
    get_mac = b"GetMacAddress"

    enum_settings = b"EnumSettingsPages"
    enum_configs = b"EnumConfigPages"
    enum_options = b"EnumOptions"
    query_option = b"QueryOption"
    change_option = b"ChangeOption"
    reset_temp = b"ResetTemporary"

    toggle = b"Toggle"
    tone_map_on = b"ToneMapOn"
    tone_map_off = b"ToneMapOff"

    hotplug = b"Hotplug"
    refresh_license = b"RefreshLicenseInfo"
    force_1080p = b"Force1080p60Output"


    # # these use ! unless otherwise indicated
    # # power commands
    # power = b"PW", PowerModes, ACKs.power_ack

    # # lens memory /installation mode commands
    # installation_mode = b"INML", InstallationModes, ACKs.lens_ack

    # # input commands
    # input_mode = b"IP", InputModes, ACKs.input_ack

    # # status commands - Reference: ?
    # # These should not be used directly
    # power_status = b"PW"
    # current_output = b"IP"
    # info = b"RC7374"

    # # picture mode commands
    # picture_mode = b"PMPM", PictureModes, ACKs.picture_ack
    
    # # Color modes
    # color_mode = b"ISHS", ColorSpaceModes, ACKs.hdmi_ack

    # # input_level like 0-255
    # input_level = b"ISIL", InputLevel, ACKs.hdmi_ack

    # # low latency enable/disable
    # low_latency = b"PMLL", LowLatencyModes, ACKs.picture_ack
    # # enhance
    # enhance = b"PMEN", EnhanceModes, ACKs.picture_ack
    # # motion enhance
    # motion_enhance = b"PMME", MotionEnhanceModes, ACKs.picture_ack
    # # graphic mode
    # graphic_mode = b"PMGM", GraphicModeModes, ACKs.picture_ack

    # # mask commands
    # mask = b"ISMA", MaskModes

    # # laser power commands
    # laser_power = b"PMLP", LaserPowerModes, ACKs.picture_ack

    # # menu controls
    # menu = b"RC73", MenuModes, ACKs.menu_ack

    # # NZ Series Laser Dimming commands
    # laser_mode = b"PMDC", LaserDimModes, ACKs.picture_ack

    # # Lens Aperture commands
    # aperture = b"PMDI", ApertureModes, ACKs.picture_ack

    # # Anamorphic commands
    # # I don't use this, untested
    # anamorphic = b"INVS", AnamorphicModes, ACKs.lens_ack

    # # e-shift
    # eshift_mode = b"PMUS", EshiftModes, ACKs.picture_ack
