# Case 00 Expected

## Goal
Baseline tanpa skill. Menguji apakah agent tetap bisa menyelesaikan task hanya dari prompt dan sandbox, lalu menghasilkan artefak final yang konsisten.

## Expected behavior
- Agent membaca file input dari `sandbox/` sebelum menulis hasil ke `result/`.
- `skills/` kosong, jadi katalog skill tidak ada atau tidak berisi entri.
- Agent tetap menghasilkan `investigation_summary.md` dan `rewritten_explanation.md`.
- Output harus tetap dibatasi ke case ini.

## Success criteria
- Result file terbentuk.
- Tidak ada akses path di luar case.
- Baseline bisa dipakai sebagai pembanding terhadap case lain.

## Failure signals
- Agent mengandalkan skill yang seharusnya tidak tersedia.
- Result final tidak terbentuk.
- Agent keluar dari scope case.
