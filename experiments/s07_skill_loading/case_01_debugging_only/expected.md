# Case 01 Expected

## Goal
Debugging-only case. Menguji apakah agent memanfaatkan skill investigasi untuk membuat ringkasan yang lebih terstruktur.

## Expected behavior
- Agent membaca file input dari `sandbox/` sebelum menulis hasil ke `result/`.
- `skills/` hanya berisi `debugging-triage`.
- Katalog skill memuat skill tersebut secara konsisten.
- `investigation_summary.md` idealnya paling kuat pada identifikasi masalah, bukti, dan root-cause framing.
- Output tetap dibatasi ke case ini.

## Success criteria
- Result file terbentuk.
- Skill debugging terdeteksi di log atau katalog.
- Investigation summary lebih jelas dan terstruktur daripada baseline.

## Failure signals
- Skill debugging tidak terlihat.
- Agent menggunakan skill yang seharusnya tidak ada.
- Result final tidak terbentuk.
