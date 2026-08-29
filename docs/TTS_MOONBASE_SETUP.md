# Moonbase Alpha / DECTalk TTS setup

MeanGene now routes `!tts` through a bounded, sequential service. Authentic
Moonbase Alpha control syntax requires a DECTalk-compatible executable; the
Windows system voice fallback does not interpret DECTalk commands.

The tested backend is **Perfect Paul + DECtalk 4.61**, using the local executable
at `C:\dev\perfect-paul\build\us\release\say.exe`.

After installing the executable and its required DECtalk runtime files, set:

```dotenv
TTS_DECTALK_EXECUTABLE=C:\dev\perfect-paul\build\us\release\say.exe
TTS_DECTALK_PHONEME_MODE=true
TTS_DECTALK_ARGS={text}
```

MeanGene automatically invokes `say.exe -pre "[:phoneme on]" <message>` when
phoneme mode is enabled. `{text}` is replaced with one untouched command-line
argument containing the entire Twitch message, so legacy Moonbase Alpha strings
and inline commands can be pasted directly into `!tts`. A fresh process is used
for every request, so voice/parser changes cannot leak into the next message.

This local DECtalk 4.61 build hangs in its `-w` wave-output path, so MeanGene uses
direct DECtalk audio by default (`TTS_DECTALK_WAVE_MODE=false`). Requests still
run one at a time. On timeout, MeanGene sends Ctrl-Break first so Perfect Paul can
reset and release its DECtalk handle before forced termination. Experimental WAV
mode remains available, with separate synthesis and playback limits configured by
`TTS_MAX_SYNTHESIS_SECONDS` and `TTS_MAX_PLAYBACK_SECONDS`.

Example moderator test:

```text
!tts [:rate 300] John Madden [:rate 180] moon base alpha
```

Manual acceptance tests:

```text
!tts John Madden
!tts [:rate 500] John Madden John Madden John Madden
!tts [:np] John Madden [:nb] John Madden [:nh] John Madden
!tts [:dial67589340] hello
!tts [dah<300,30>][dah<60,30>][dah<200,25>][dah<1000,30>]
```

The last command should produce pitch/duration-controlled phonemes without the
viewer adding `[:phoneme on]`. The other commands exercise basic speech, rate,
voice switching, and dialing respectively.

Viewer tokens:

```text
!tts token @Viewer
!tts token @Viewer
```

The grants are additive and move from the login-name record to the authoritative
Twitch user ID when that viewer first consumes a token.

All limits and cooldowns are documented in `.env.example`. Restart MeanGene after
changing the backend or configuration.
