# Case 03 Expected

## Goal
Both-skills case. Menguji apakah agent melihat dua skill sekaligus dan punya kesempatan menggabungkan gaya investigasi dan penulisan.

## Expected behavior
- Agent membaca file input dari `sandbox/` sebelum menulis hasil ke `result/`.
- `skills/` berisi `debugging-triage` dan `technical-writing`.
- Katalog skill memuat dua entri dengan urutan stabil.
- Output idealnya menunjukkan kombinasi struktur investigasi yang rapi dan rewrite yang jelas.
- Output tetap dibatasi ke case ini.

## Success criteria
- Result file terbentuk.
- Kedua skill terlihat di katalog atau log.
- Hasil akhir paling lengkap di antara case lain.

## Failure signals
- Salah satu skill hilang dari katalog.
- Agent tidak membedakan case ini dari single-skill case.
- Result final tidak terbentuk.
