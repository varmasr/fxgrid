import MetaTrader5 as mt5
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

# Load .env from current directory
load_dotenv()

# Use your actual env var names
LOGIN_STR = os.getenv("ICT_STREAM_LOGIN")
PASSWORD = os.getenv("ICT_STREAM_PASSWORD")
SERVER = os.getenv("ICT_STREAM_SERVER")

if not LOGIN_STR or not PASSWORD or not SERVER:
    print("❌ Missing one or more required env vars:")
    print("  ICT_STREAM_LOGIN =", LOGIN_STR)
    print("  ICT_STREAM_PASSWORD =", "SET" if PASSWORD else "NOT SET")
    print("  ICT_STREAM_SERVER =", SERVER)
    raise SystemExit(1)

try:
    LOGIN = int(LOGIN_STR)
except ValueError:
    print(f"❌ ICT_STREAM_LOGIN is not a valid integer: {LOGIN_STR!r}")
    raise SystemExit(1)

SYMBOL = "EURUSD"

print("\n=== Connecting to MT5 ===")
if not mt5.initialize():
    print("❌ MT5 initialization failed:", mt5.last_error())
    raise SystemExit(1)

authorized = mt5.login(LOGIN, PASSWORD, SERVER)
if not authorized:
    print("❌ MT5 login failed:", mt5.last_error())
    mt5.shutdown()
    raise SystemExit(1)

print(f"✅ Connected to MT5: login={LOGIN}, server={SERVER}")
print(f"Symbol: {SYMBOL}")

# --- Time diagnostics: local vs UTC offset ---
local_now = datetime.now()
utc_now = datetime.utcnow()
offset = local_now - utc_now
offset_hours = offset.total_seconds() / 3600.0

print("\n=== Time Diagnostics ===")
print(f"Local PC time:       {local_now}")
print(f"UTC time (python):   {utc_now}")
print(f"Local - UTC offset:  {offset}  (~{offset_hours:.2f} hours)")

print("\n=== Fetching latest tick and M1 candle ===")

# Latest tick (for reference)
tick = mt5.symbol_info_tick(SYMBOL)
if tick is None:
    print("❌ Failed to get tick:", mt5.last_error())
    mt5.shutdown()
    raise SystemExit(1)

tick_epoch = tick.time
tick_local = datetime.fromtimestamp(tick_epoch)
tick_utc = datetime.utcfromtimestamp(tick_epoch).replace(tzinfo=timezone.utc)

print("\n--- Tick time ---")
print(f"Tick epoch:          {tick_epoch}")
print(f"Tick as local time:  {tick_local}")
print(f"Tick as UTC time:    {tick_utc}")

# Latest 2 M1 candles
rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 2)
if rates is None or len(rates) == 0:
    print("❌ Failed to get M1 candles:", mt5.last_error())
    mt5.shutdown()
    raise SystemExit(1)

latest = rates[-1]
prev = rates[-2] if len(rates) > 1 else None

def show_candle(label, r):
    epoch = r["time"]

    # How MT5 / Python local sees it (this matches chart time)
    candle_local = datetime.fromtimestamp(epoch)

    # How we will store it in DB: UTC
    candle_utc = datetime.utcfromtimestamp(epoch).replace(tzinfo=timezone.utc)

    # Simulated "read from DB and show in local time again"
    candle_db_local = candle_utc.astimezone()

    print(f"\n{label}")
    print(f"  Raw epoch:              {epoch}")
    print(f"  Local time (chart):     {candle_local}")        # should match MT5 Data Window time
    print(f"  UTC for DB (to store):  {candle_utc}")         # this is what we want in live_market_data_m1
    print(f"  DB->local round trip:   {candle_db_local}")    # should equal candle_local

    print(f"  O: {r['open']}")
    print(f"  H: {r['high']}")
    print(f"  L: {r['low']}")
    print(f"  C: {r['close']}")
    if 'real_volume' in r.dtype.names:
        print(f"  Real Volume: {r['real_volume']}")
    if 'tick_volume' in r.dtype.names:
        print(f"  Tick Volume: {r['tick_volume']}")

show_candle("Prev EURUSD M1 candle", prev)
show_candle("Latest EURUSD M1 candle", latest)

print("\n=== Raw latest structure ===")
print(latest)

mt5.shutdown()
print("\n✅ Done. Compare:")
print("  - 'Local time (chart)' vs MT5 Data Window time")
print("  - O/H/L/C vs MT5 latest candle O/H/L/C")
print("If these match, storing 'UTC for DB' is the correct behavior.")
