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
| `language_code` | Sahara/ASR input language hint | `sw` |
| `domain` | Scenario domain | `healthcare` |
| `accent_country` | Speaker accent / country | `Kenya` |
| `device_type` | Recording device | `smartphone` |
| `noise_condition` | Background noise | `clinic background noise` |
| `reference_transcript` | Exact words spoken (ground truth, code-switching included) | `"Nina homa kali tangu jana na headache mbaya sana"` |
| `switch_points` | JSON boundaries; `token_index` is the number of reference tokens before the switch | `[{"token_index":4,"from_language":"sw","to_language":"en"}]` |
| `expected_topic` | Gold triage topic | `Fever / possible infection (malaria, typhoid, etc.)` |
| `expected_urgency` | Gold urgency label | `URGENT` |
| `expected_department` | Gold routing destination | `General Outpatient / Internal Medicine` |
| `expected_slots` | JSON object of intake-card fields and gold values | `{}` |
| `expected_entities` | JSON list of gold entities/findings | `["Kisumu", "malaria"]` |

These clips serve two purposes:

1. Input to the Model Benchmark tab (upload the clip + paste the
   `reference_transcript` to score Intron Sahara vs Whisper vs MMS).
2. The challenge's audio-sample submission requirement ("submit the
   code-switched audio samples used for testing, with basic metadata").

Recording tips: mix languages naturally mid-sentence, vary noise conditions
(quiet room vs busy clinic), and cover at least 2-3 different language pairs.

Run the full report from the project root with `python3 -m
scripts.generate_benchmark_report --agentic`. Without `--agentic`, the batch
uses Sahara plain transcription and still reports ASR, switch-point, and RTF
metrics. Do not report switch-point or downstream aggregates for clips without
the corresponding gold annotations. Record the machine, model sizes, API
region, and network condition with each run.
