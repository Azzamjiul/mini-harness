# Case 02 Expected

## Goal
Writing-only case. Menguji apakah agent memanfaatkan skill penulisan untuk membuat rewrite yang lebih rapi, jelas, dan terstruktur.

## Expected behavior
- Agent membaca file input dari `sandbox/` sebelum menulis hasil ke `result/`.
- `skills/` hanya berisi `technical-writing`.
- Katalog skill memuat skill tersebut secara konsisten.
- `rewritten_explanation.md` idealnya paling kuat pada struktur, kejelasan, dan pemisahan fakta versus interpretasi.
- Output tetap dibatasi ke case ini.

## Success criteria
- Result file terbentuk.
- Skill writing terdeteksi di log atau katalog.
- Rewritten explanation lebih rapi dan mudah dipindai daripada baseline.

## Failure signals
- Skill writing tidak terlihat.
- Agent menggunakan skill yang seharusnya tidak ada.
- Result final tidak terbentuk.
