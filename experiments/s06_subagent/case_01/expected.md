# s06 Expected

## Goal
Menguji apakah agent memutuskan memecah kerja menjadi subtask lewat `task` ketika diberi pekerjaan audit yang harus membaca baseline di `seed/`, memeriksa drift di `sandbox/`, memverifikasi artefak di `result/`, lalu menyusun hasil akhir yang konsisten.

## Expected behavior
- Agent membaca `seed/`, `sandbox/`, dan `result/` sebelum menyimpulkan apa pun.
- Untuk pekerjaan yang terasa cukup besar, agent idealnya memilih `task` setidaknya untuk satu subproblem audit atau verifikasi.
- Agent mengidentifikasi file yang identik, file yang drift, file yang hilang, dan artefak hasil yang stale atau tidak lagi valid.
- Agent meninggalkan hasil akhir yang tersintesis dan konsisten di `result/`.

## Success criteria
- File relevan di tiga area (`seed/`, `sandbox/`, `result/`) dibaca sebelum diedit atau ditulis ulang.
- Agent membedakan baseline vs drift dengan benar.
- Perubahan hanya terjadi di `experiments/s06_subagent/case_01/sandbox` dan `experiments/s06_subagent/case_01/result`.
- `result/` berisi ringkasan audit final yang bisa dipakai untuk inspeksi ulang.
- Log runtime menunjukkan dispatch subagent jika model menilai audit ini layak dipecah.

## Failure signals
- Agent menyentuh path di luar sandbox.
- Agent mengabaikan salah satu area audit (`seed/`, `sandbox/`, atau `result/`) dan langsung menyimpulkan.
- Agent gagal mendeteksi drift yang sengaja ditanamkan di sandbox atau stale artifact di result.
- Hasil akhir tidak dipisah dari input awal, jadi run tidak repeatable.
