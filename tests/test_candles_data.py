from datetime import datetime, timedelta, timezone
from pa_engine.db.candles import load_m1_candles

end = datetime.now(timezone.utc)
start = end - timedelta(hours=2)

df = load_m1_candles("USDJPY", start, end)
print(df.tail())
print(df.dtypes)
