# Moonbase Alpha / DECTalk TTS setup

MeanGene now routes `!tts` through a bounded, sequential service. Authentic
Moonbase Alpha control syntax requires a DECTalk-compatible executable; the
Windows system voice fallback does not interpret DECTalk commands.

One compatible command-line frontend is `say.exe` from the
[Perfect Paul project](https://github.com/jmcgover/perfect-paul). The maintained
[DECtalk source project](https://github.com/dectalk/dectalk) also provides modern
builds and build instructions.

After installing the executable and its required DECtalk runtime files, set:

```dotenv
TTS_DECTALK_EXECUTABLE=C:\DECTalk\say.exe
TTS_DECTALK_ARGS=-pre [:np] {text}
TTS_DEFAULT_VOICE=paul
```

`{text}` is replaced with one untouched command-line argument containing the
entire Twitch message. `[:np]` resets each new process to Perfect Paul before
processing message-specific commands. A fresh process is used for every request,
so voice/parser changes cannot leak into the next message.

Example moderator test:

```text
!tts [:rate 300] John Madden [:rate 180] moon base alpha
```

Viewer tokens:

```text
!tts token @Viewer
!tts token @Viewer
```

The grants are additive and move from the login-name record to the authoritative
Twitch user ID when that viewer first consumes a token.

All limits and cooldowns are documented in `.env.example`. Restart MeanGene after
changing the backend or configuration.
