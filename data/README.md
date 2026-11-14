# Real datasets (download on a machine with internet, then commit here)

1. data/anonymous_bank/  Technion SEE Center "Anonymous Bank" call centre (1999), one year of calls.
   Download: https://see-center.iem.technion.ac.il/databases/AnonymousBank/Data/AnonymousBank.rar
   Extract the monthly text files into this folder. Credit: SEE Center, Technion (Mandelbaum et al.).
   Run: python -m engine.realdata
   If the files are large, commit 2-3 months only, or add a .gitignore and commit just the results JSON.

2. data/weather/bengaluru_hourly.csv  real hourly temperature (Open-Meteo, free, no key).
   Example (historical): https://archive-api.open-meteo.com/v1/archive?latitude=12.97&longitude=77.59&start_date=2026-04-01&end_date=2026-04-30&hourly=temperature_2m&timezone=Asia%2FKolkata
   Save as CSV with columns: time,temperature_c. Credit: Open-Meteo.com (CC BY 4.0).

3. data/ev_sessions/  a public EV charging sessions dataset (e.g. a city open-data portal; check licence).
   Needed columns: start time, end time / charging time, energy kWh. Note the source URL in this file.
