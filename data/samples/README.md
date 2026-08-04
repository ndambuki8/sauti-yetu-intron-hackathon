# Code-switched test samples

Record your own code-switched clips (<= 120 seconds each, WAV/MP3/M4A/OGG/WebM/FLAC)
and register them in `metadata.csv`. The three rows already in the CSV are
placeholders showing the expected format — replace them with your real recordings
before submission.

## metadata.csv columns

| Column | Description | Example |
| --- | --- | --- |
| `filename` | Audio file name in this folder | `sample_sw_en_fever.wav` |
| `language_pair` | Languages mixed in the clip | `Swahili-English` |
| `domain` | Scenario domain | `healthcare` |
| `accent_country` | Speaker accent / country | `Kenya` |
| `device_type` | Recording device | `smartphone` |
| `noise_condition` | Background noise | `clinic background noise` |
| `reference_transcript` | Exact words spoken (ground truth, code-switching included) | `"Nina homa kali tangu jana na headache mbaya sana"` |

These clips serve two purposes:

1. Input to the Model Benchmark tab (upload the clip + paste the
   `reference_transcript` to score Intron Sahara vs Whisper vs MMS).
2. The challenge's audio-sample submission requirement ("submit the
   code-switched audio samples used for testing, with basic metadata").

Recording tips: mix languages naturally mid-sentence, vary noise conditions
(quiet room vs busy clinic), and cover at least 2-3 different language pairs.
