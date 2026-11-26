# Chattogram Rain & Waterlogging Alert Bot 🌧️🇧🇩

Free **Telegram alerts in Bengali** when heavy rain (and with it waterlogging) is likely in Chattogram, plus a small
live status page. Everything runs on **GitHub Actions cron**: no server, no paid API, no API key for the weather data.

```
🔴 চট্টগ্রাম: জলাবদ্ধতার উচ্চ ঝুঁকি
সবচেয়ে ভারী বৃষ্টি: আজ বিকেল ৫টা থেকে ৩ ঘণ্টা
৩ ঘণ্টায় সম্ভাব্য বৃষ্টি: ৩৬ মিমি (কোনো মডেলে সর্বোচ্চ ৪৮ মিমি)
🌊 ভারী বৃষ্টির সময় জোয়ার — পানি নামতে দেরি হতে পারে।
🔴 মুরাদপুর … 🟠 আগ্রাবাদ … 
```

## How it works
1. **Forecast:** every 3 hours, [Open-Meteo](https://open-meteo.com/) is queried for six waterlogging-prone areas
   (Muradpur, Chawkbazar, Bakalia, Agrabad, Halishahar, Patenga). One call returns three models: ECMWF IFS, NOAA GFS and
   DWD ICON. The **median** across models is the "likely" amount and the **maximum** is the worst case.
2. **Tide:** the Open-Meteo Marine API's `sea_level_height_msl` near the Karnaphuli mouth marks high-tide windows.
   Rain at high tide drains slowly, so the threshold for "high" risk is lower then.
3. **Risk level** (thresholds in `config.toml`). The 24-hour limits follow the Bangladesh Meteorological Department
   categories (moderately heavy 23–43 mm, heavy 44–88 mm, very heavy ≥ 89 mm), and 3-hour limits catch short
   cloudbursts:

   | Level | Next 3 h | Next 24 h |
   |---|---|---|
   | 🟡 low | ≥ 10 mm | ≥ 23 mm |
   | 🟠 medium | ≥ 25 mm | ≥ 44 mm |
   | 🔴 high | ≥ 50 mm, or ≥ 30 mm at high tide | ≥ 89 mm |
4. **No spam:** the bot sends an alert when the risk reaches medium or rises, a reminder every 6 h while it lasts, an
   all-clear when it ends, and one morning summary per day. This memory lives in `state/state.json`, which the
   workflow commits back.
5. **Status page:** `docs/status.json` and `docs/index.html` (GitHub Pages) show the current level per area and an
   hourly rain chart, in Bengali.

## Setup (10 minutes)
1. **Telegram bot:** message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the **token**.
   - **Chat ID** for yourself or a group: send the bot a message, open
     `https://api.telegram.org/bot<TOKEN>/getUpdates`, and copy `chat.id` (groups have negative IDs).
   - For a **channel**, add the bot as an admin and use `@your_channel_name`. Several targets can be separated by commas.
2. Repo → **Settings → Secrets and variables → Actions** → add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
3. **Workflows:** move `alert.yml`, `backtest.yml` and `ci.yml` into `.github/workflows/`.
4. **Actions** tab → *rain-alert* → **Run workflow** once. To check only the bot, run
   `python -m src.main test-message` locally with the two secrets set as environment variables.
5. *(optional)* **Settings → Pages → Deploy from a branch → `main` / `/docs`** for the status page.

GitHub pauses scheduled workflows in repos with no activity for 60 days. The workflow commits its state on every
run, and also calls the workflow "enable" API, to stay active. If it ever pauses, press *Enable workflow* in the
Actions tab.

## Tune the thresholds with history
```bash
pip install -r requirements.txt
python -m src.main backtest --start 2010-01-01 --end 2024-12-31   # -> results/backtest.md
python -m src.main preview                                         # the alert that would be sent right now
python -m src.main run --dry-run                                   # full run, prints instead of sending
```
The back-test uses Open-Meteo's historical reanalysis (hourly, about 10–25 km grid) and counts how many days per year
each level would have fired. Reanalysis smooths short, intense storms, so treat its counts as a lower bound. The
same workflow is available as *Actions → backtest*.

## Tests
`python -m pytest -q`: Open-Meteo and Telegram are mocked. The tests cover multi-model parsing, every risk rule
including the tide rule, the no-spam logic, the Bengali message and status page, and the back-test.

## Notes
- Open-Meteo is free for **non-commercial** use (CC BY 4.0 data), with fair-use limits. Eight calls a day is far
  below them. Credit Open-Meteo if you republish the forecasts.
- This is **not an official warning**. Always follow the Bangladesh Meteorological Department and city authorities.
  Waterlogging also depends on drains, canal work and local blockages, which no weather model sees.
- Code: MIT.
