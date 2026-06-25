# Case 01 Expected

## Goal
Menguji apakah agen akan memulai dengan `todo_write` saat diberi tugas multi-step yang jelas.

## Expected behavior
- Turn awal seharusnya cenderung memanggil `todo_write`.
- Setelah itu agen semestinya melakukan inspeksi sandbox dengan tool baca/list.
- Agen kemudian harus:
  - membaca `brief.md` dan `notes.md`,
  - mengedit `notes.md`,
  - membuat `output/summary.md`,
  - menghapus `obsolete.txt`,
  - memverifikasi hasil akhir.

## Success criteria
- Ada `todo_write` di awal atau sangat dekat dengan awal.
- Semua perubahan hanya terjadi di `experiments/s05_todo_write/case_01/sandbox`.
- Tidak ada file di luar sandbox yang disentuh.

## Failure signals
- Agen langsung kerja tanpa plan padahal task multi-step.
- Agen menyentuh path di luar sandbox.
- Agen tidak melakukan verifikasi akhir.
