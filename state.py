_twitch_channel = None

def set_twitch_channel(channel):
    global _twitch_channel
    _twitch_channel = channel

def get_twitch_channel():
    return _twitch_channel
