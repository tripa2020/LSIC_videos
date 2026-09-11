# URL-mode A/B — yt_cpGQa5Q4yII (70 min, 3 speakers) — 2026-09-11

Same video, same code, two ingest modes. Download mode = July's yt-dlp + Opus-chunk ASR + keyframe VLM
(`Report_all/2_Robotics_Pioneers_…__yt_cpGQa5Q4yII`). URL mode = `YT_INPUT=url`: Gemini reads the public
YouTube URL server-side with 300 s offsets; nothing downloaded (this folder).

| metric                 | download (July) | URL mode (this) |
|------------------------|-----------------|-----------------|
| transcript segments    | 794             | 983             |
| transcript words       | 15,564          | 14,227          |
| vocabulary Jaccard     | —               | 0.84            |
| captions (visual)      | 107             | 116             |
| eval gates             | 6/6             | 6/6             |
| cites / decile cov     | 97 / 1.0        | 73 / 1.0        |
| moves / founder plays  | 16 / 4          | 15 / 4          |
| quotes verified        | 1.0             | 1.0             |
| final-third cites      | 3               | 6               |
| notes.md               | 45 KB           | 43 KB           |
| ingest wall            | download + ffmpeg | 7 s (duration probe, exact) |
| transcribe wall        | —               | 30 s (15 windows × 12-way) |
| visual wall            | —               | 647 s (4 read-timeouts, all retried OK) |

Defect found + guarded: 1 of 15 transcript windows came back with collapsed timestamps (76 segments in a
5 s span; text complete). `url_media._collapsed` now re-issues such a window once and spreads evenly as a
last resort; the live re-issue of that window returned a correct 3965→4192 s span. This bundle's notes
were generated BEFORE the guard (citations in 3900–4200 s approximate).
