from __future__ import annotations

from io import BytesIO
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

st.set_page_config(page_title="StockTrack | Stock Analysis", page_icon="📈", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
html, body, [class*="css"] {font-family:'DM Sans',sans-serif;}
[data-testid="stAppViewContainer"], [data-testid="stHeader"] {background:#0b1220; color:#e6edf7;}
[data-testid="stSidebar"] {background:#111b2e;}
[data-testid="stSidebar"] * {color:#edf3fc !important;}
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"], label, p {color:#d4deed;}
[data-testid="stMetric"] {background:#151f31; border:1px solid #29364b; padding:18px 20px; border-radius:14px; box-shadow:0 3px 14px rgba(0,0,0,.18);}
[data-testid="stMetricLabel"] {color:#9aabc2;}
[data-testid="stMetricValue"] {color:#f0f5fc; font-family:'Manrope',sans-serif;}
[data-testid="stFileUploader"] section {background:#151f31; border:1px dashed #40516b;}
[data-testid="stFileUploader"] small, [data-testid="stFileUploader"] span {color:#c4d1e4;}
[data-baseweb="select"] > div, [data-baseweb="input"] > div, [data-testid="stNumberInput"] input {background:#151f31; color:#e6edf7; border-color:#34445c;}
[data-testid="stDataFrame"], [data-testid="stTable"] {background:#151f31;}
[data-testid="stAlert"] {background:#151f31; color:#e6edf7;}
.block-container {padding-top:2rem; max-width:1500px;}
.hero {padding:26px 30px; border-radius:18px; color:white; background:linear-gradient(110deg,#101a2b,#203f64); margin-bottom:22px;}
.hero h1 {font-family:'Manrope',sans-serif; font-size:2rem; margin:0 0 6px 0; color:white;}
.hero p {color:#bdcce0; margin:0;}
.section-title {font-family:'Manrope',sans-serif; font-weight:700; font-size:1.2rem; margin:8px 0 12px;}
.note {font-size:.85rem; color:#9aabc2;}
.upload-panel {padding:18px 22px; margin-bottom:20px; border-radius:14px; background:#111b2e; border:1px solid #29364b;}
.upload-panel h3 {margin:0 0 8px; color:#f0f5fc; font-family:'Manrope',sans-serif;}
</style>
""", unsafe_allow_html=True)

st.sidebar.markdown("# STOCKTRACK")
st.sidebar.caption("STOCK ANALYSIS WORKSPACE")
st.sidebar.markdown("---")
page = st.sidebar.radio("WORKSPACE", ["Overview", "Price & Returns", "Profit / Loss", "Forecast", "Data Explorer", "Live Crypto.com"], label_visibility="collapsed")
st.sidebar.markdown("---")

st.markdown('<div class="hero"><h1>Stock market analysis</h1><p>Explore price action, historical performance, and a transparent trend-based outlook.</p></div>', unsafe_allow_html=True)
st.markdown('<div class="upload-panel"><h3>Upload market data</h3></div>', unsafe_allow_html=True)
upload = st.file_uploader("Choose a CSV or Excel file", type=["csv", "xlsx"], label_visibility="collapsed")
st.caption("CSV or Excel · Your data stays in this session")

@st.cache_data(ttl=30, show_spinner=False)
def crypto_request(method, params):
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=retry))
        response = session.get(
            "https://api.crypto.com/exchange/v1/" + method,
            params=params,
            timeout=20,
        )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code", 0) != 0:
        raise RuntimeError(payload.get("message", f"Crypto.com API error: {payload.get('code')}"))
    return payload.get("result", {})

def gemini_advisor_reply(api_key, market_summary, conversation, question):
    transcript = "\n".join(
        f"{'User' if message['role'] == 'user' else 'Advisor'}: {message['content']}"
        for message in conversation[-12:]
    )
    prompt = (
        f"Verified uploaded-data summary:\n{market_summary}\n\n"
        f"Recent conversation:\n{transcript or '(none)'}\n\n"
        f"User's question:\n{question}"
    )
    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
        headers={"x-goog-api-key": api_key},
        json={
            "system_instruction": {
                "parts": [{
                    "text": (
                        "You are MarketLens's educational financial-information assistant, not a "
                        "licensed financial adviser. Use the supplied summary as user-provided "
                        "historical data, and distinguish it from general information. Never invent "
                        "live prices, news, account holdings, income, liabilities, goals, or risk "
                        "tolerance. State when requested facts are unavailable. Do not guarantee "
                        "returns or tell the user to buy or sell. For questions about managing "
                        "profits or balances, explain general options and tradeoffs without assuming "
                        "the hypothetical capital is their actual account balance. Keep answers "
                        "clear and concise, and quote supplied figures accurately."
                    )
                }]
            },
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 768},
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Gemini returned an unexpected response.")
    if payload.get("error"):
        raise RuntimeError(payload["error"].get("message", "Gemini returned an API error."))
    candidates = payload.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini did not return an answer. Try rephrasing your question.")
    parts = candidates[0].get("content", {}).get("parts", [])
    answer = "\n".join(part["text"] for part in parts if isinstance(part.get("text"), str)).strip()
    if not answer:
        raise RuntimeError("Gemini returned no text answer. Try rephrasing your question.")
    return answer

if page == "Live Crypto.com":
    st.markdown('<div class="section-title">Crypto.com Exchange · Live market data</div>', unsafe_allow_html=True)
    st.caption("Public spot-market data from Crypto.com Exchange. No API key is required for these read-only endpoints.")
    pair_col, frame_col, refresh_col = st.columns([2, 1, 1])
    with pair_col:
        instrument = st.selectbox("Trading pair", ["BTC_USDT", "ETH_USDT", "CRO_USD", "SOL_USDT", "XRP_USDT", "BTC_USD", "ETH_USD", "ADA_USDT", "DOGE_USDT", "LINK_USDT"])
    with frame_col:
        timeframe = st.selectbox("Candle interval", ["1m", "5m", "15m", "1h", "2h", "4h", "12h", "1D", "7D", "14D", "1M"], index=3)
    with refresh_col:
        st.write("")
        if st.button("Refresh live data", use_container_width=True):
            crypto_request.clear()
            st.rerun()
    try:
        with st.spinner(f"Fetching {instrument} market data from Crypto.com…"):
            ticker_result = crypto_request("public/get-tickers", {"instrument_name": instrument})
            candle_result = crypto_request("public/get-candlestick", {"instrument_name": instrument, "timeframe": timeframe, "count": 50})
        ticker_raw = ticker_result.get("data", ticker_result)
        ticker = ticker_raw[0] if isinstance(ticker_raw, list) and ticker_raw else ticker_raw
        candles_raw = candle_result.get("data", [])
        candles = pd.DataFrame(candles_raw).rename(columns={
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume",
            "t": "timestamp",
        })
        if not ticker or candles.empty:
            st.warning("Crypto.com returned no market data for this pair and interval. Try another spot pair.")
            st.stop()
        for col in ["open", "high", "low", "close", "volume", "volume_usd"]:
            if col in candles:
                candles[col] = pd.to_numeric(candles[col], errors="coerce")
        candles["timestamp"] = pd.to_datetime(candles["timestamp"], unit="ms", utc=True, errors="coerce")
        candles = candles.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
        latest = float(ticker.get("a") or ticker.get("last") or candles["close"].iloc[-1])
        change = float(ticker.get("c") or ticker.get("change") or 0) * 100
        high_24h = float(ticker.get("h") or ticker.get("high") or candles["high"].max())
        low_24h = float(ticker.get("l") or ticker.get("low") or candles["low"].min())
        volume_24h = float(ticker.get("v") or ticker.get("volume") or 0)
        value_24h = float(ticker.get("vv") or ticker.get("volume_value") or 0)
        bid_value = ticker.get("b", ticker.get("best_bid"))
        ask_value = ticker.get("k", ticker.get("best_ask"))
        bid = float(bid_value) if bid_value is not None else None
        ask = float(ask_value) if ask_value is not None else None
        spread = ((ask / bid) - 1) * 10000 if bid and ask and bid > 0 and ask > 0 else None
        k1,k2,k3,k4,k5 = st.columns(5)
        k1.metric("Last traded price", f"{latest:,.4f}", f"{change:+.2f}% · 24h")
        k2.metric("24h high / low", f"{high_24h:,.4f} / {low_24h:,.4f}")
        k3.metric("24h base volume", f"{volume_24h:,.4f}")
        k4.metric("24h traded value", f"{value_24h:,.2f}")
        k5.metric(
            "Best bid / ask spread",
            f"{spread:.2f} bps" if spread is not None else "—",
            f"{bid:,.4f} / {ask:,.4f}" if bid is not None and ask is not None else "Bid/ask unavailable",
        )

        candle_fig = go.Figure(go.Candlestick(x=candles["timestamp"], open=candles["open"], high=candles["high"], low=candles["low"], close=candles["close"], name=instrument))
        candle_fig.update_layout(template="plotly_dark", height=460, xaxis_rangeslider_visible=False, xaxis_title="Time (UTC)", yaxis_title="Quote price", margin=dict(l=10,r=10,t=20,b=10))
        st.plotly_chart(candle_fig, use_container_width=True)

        candles["Return"] = candles["close"].pct_change()
        candles["Cumulative return"] = (1 + candles["Return"].fillna(0)).cumprod() - 1
        candles["P&L per 1,000 quote units"] = 1000 * candles["Cumulative return"]
        valid_returns = candles["Return"].dropna()
        c1,c2,c3,c4 = st.columns(4)
        c1.metric(f"Interval return · {len(candles)-1} periods", f"{(candles['close'].iloc[-1]/candles['close'].iloc[0]-1):+.2%}" if len(candles)>1 else "—")
        c2.metric("Peak-to-trough drawdown", f"{((candles['close']/candles['close'].cummax()-1).min()):.2%}")
        c3.metric("Interval range", f"{candles['low'].min():,.4f} – {candles['high'].max():,.4f}")
        c4.metric("Mean candle volume", f"{candles['volume'].mean():,.4f}" if "volume" in candles else "—")
        st.markdown('<div class="section-title">Recent OHLCV candles</div>', unsafe_allow_html=True)
        show_cols=[c for c in ["timestamp","open","high","low","close","volume","volume_usd"] if c in candles.columns]
        st.dataframe(candles[show_cols].sort_values("timestamp",ascending=False).head(20),use_container_width=True,hide_index=True)
        observed=ticker.get("t") or ticker.get("timestamp")
        observed_text = (
            pd.to_datetime(int(observed), unit="ms", utc=True).strftime("%Y-%m-%d %H:%M:%S UTC")
            if observed else "not provided"
        )
        st.caption(f"Source: Crypto.com Exchange public API · {instrument} · {timeframe} candles · {len(candles)} candles returned · Ticker timestamp: {observed_text}")
        st.warning("Market data is informational only and may be delayed or incomplete. Candle-based returns and drawdowns describe only the candles returned, not a complete backtest. No investment advice.")
    except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError) as exc:
        st.error(f"Could not load Crypto.com data: {exc}")
        st.info("Check your internet connection and confirm the selected pair is supported by Crypto.com Exchange.")
    st.stop()

if upload is None:
    st.info("Upload a CSV or Excel file to begin. For best results, include a date column and a closing-price column (for example: Date, Close).")
    st.markdown("### What this dashboard does")
    a,b,c=st.columns(3)
    a.markdown("**01 · Inspect**  \nReview your data, column types, and missing values.")
    b.markdown("**02 · Understand**  \nAnalyze price movement, returns, volatility, and hypothetical P&L.")
    c.markdown("**03 · Explore**  \nView an illustrative linear-trend projection—not investment advice.")
    st.stop()

try:
    if upload.name.lower().endswith(".csv"):
        data = pd.read_csv(upload)
    else:
        data = pd.read_excel(upload)
except Exception as exc:
    st.error(f"Could not read this file: {exc}")
    st.stop()

if data.empty:
    st.error("The uploaded file has no rows.")
    st.stop()
data.columns = [str(c).strip() for c in data.columns]
def find_column(candidates):
    mapping = {str(c).strip().lower().replace("_", " "): c for c in data.columns}
    for candidate in candidates:
        key = candidate.lower().replace("_", " ")
        if key in mapping:
            return mapping[key]
    return None

date_guess = find_column(["date", "datetime", "timestamp", "time", "trading date"])
close_guess = find_column(["close", "adj close", "adjusted close", "closing price", "price", "last", "close price"])
volume_guess = find_column(["volume", "vol"])

with st.sidebar.expander("Column mapping", expanded=not bool(close_guess)):
    date_col = st.selectbox("Date column (optional)", ["— None —"] + list(data.columns), index=(list(data.columns).index(date_guess)+1 if date_guess in data.columns else 0))
    price_col = st.selectbox("Price column", list(data.columns), index=(list(data.columns).index(close_guess) if close_guess in data.columns else 0))
    date_col = None if date_col == "— None —" else date_col
    capital = st.number_input("Hypothetical starting capital", min_value=1.0, value=10000.0, step=1000.0)

work = data.copy()
if date_col:
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
    work = work.dropna(subset=[date_col]).sort_values(date_col)
work[price_col] = pd.to_numeric(work[price_col].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")
work = work.dropna(subset=[price_col])
work = work[work[price_col] > 0].copy()
if work.empty:
    st.error("No valid positive prices were found in the selected price column. Check the column mapping and source data.")
    st.stop()

price = work[price_col].astype(float).reset_index(drop=True)
work = work.reset_index(drop=True)
work["Return"] = price.pct_change()
work["Cumulative Return"] = (1 + work["Return"].fillna(0)).cumprod() - 1
work["Hypothetical P&L"] = capital * work["Cumulative Return"]
first, last = float(price.iloc[0]), float(price.iloc[-1])
total_return = last / first - 1
periods = max(len(price)-1, 0)
annualized = ((last/first) ** (252/periods) - 1) if periods > 0 else 0.0
vol = float(work["Return"].dropna().std() * np.sqrt(252)) if periods > 1 else 0.0
max_dd = float(((price / price.cummax()) - 1).min())
index = work[date_col] if date_col else pd.RangeIndex(1, len(work)+1, name="Observation")

st.caption(f"**{upload.name}** · {len(work):,} valid price observations · Price column: `{price_col}`" + (f" · {work[date_col].min():%d %b %Y} – {work[date_col].max():%d %b %Y}" if date_col else ""))

if page == "Overview":
    st.markdown('<div class="section-title">Performance snapshot</div>', unsafe_allow_html=True)
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Latest price", f"{last:,.2f}", f"{(price.iloc[-1]/price.iloc[-2]-1):+.2%}" if len(price)>1 else None)
    m2.metric("Total price return", f"{total_return:+.2%}")
    m3.metric("Annualized volatility*", f"{vol:.2%}")
    m4.metric("Maximum drawdown", f"{max_dd:.2%}")
    st.markdown("<br>", unsafe_allow_html=True)
    fig=go.Figure(go.Scatter(x=index,y=price,mode="lines",name="Price",line=dict(color="#2f80ed",width=2.5),fill="tozeroy",fillcolor="rgba(47,128,237,.08)"))
    fig.update_layout(template="plotly_dark",height=400,margin=dict(l=10,r=10,t=20,b=10),xaxis_title="Date" if date_col else "Observation",yaxis_title="Price",hovermode="x unified")
    st.plotly_chart(fig,use_container_width=True)
    left,right=st.columns(2)
    with left:
        st.markdown('<div class="section-title">Return distribution</div>',unsafe_allow_html=True)
        r=work["Return"].dropna()
        if len(r):
            f=go.Figure(go.Histogram(x=r*100,nbinsx=35,marker_color="#50b89b")); f.update_layout(template="plotly_dark",height=300,xaxis_title="Daily return (%)",yaxis_title="Sessions",margin=dict(l=5,r=5,t=10,b=5)); st.plotly_chart(f,use_container_width=True)
    with right:
        st.markdown('<div class="section-title">At a glance</div>',unsafe_allow_html=True)
        st.write(f"- **Starting price:** {first:,.2f}\n- **Period high / low:** {price.max():,.2f} / {price.min():,.2f}\n- **Annualized return estimate:** {annualized:+.2%}\n- **Best single-period return:** {work['Return'].max():+.2%}" if periods else f"- **Starting price:** {first:,.2f}\n- **Period high / low:** {price.max():,.2f} / {price.min():,.2f}")
    st.caption("*Annualization assumes approximately 252 trading observations per year; it is descriptive and sensitive to the sample period.")
    st.markdown('<div class="section-title">AI advisor · data-grounded guide</div>',unsafe_allow_html=True)
    date_summary = (
        f"{work[date_col].min():%d %b %Y} to {work[date_col].max():%d %b %Y}"
        if date_col else "dates not provided"
    )
    advisor_context = "\n".join([
        f"Selected price column: {price_col}",
        f"Observations: {len(work):,}; sample period: {date_summary}",
        f"Latest uploaded price: {last:,.4f}",
        f"Price return over the uploaded sample: {total_return:+.2%}",
        f"Annualized volatility estimate: {vol:.2%}",
        f"Maximum historical drawdown in the sample: {max_dd:.2%}",
        f"Sample high / low: {price.max():,.4f} / {price.min():,.4f}",
        f"Hypothetical starting capital selected in the app: {capital:,.2f}",
        f"Hypothetical ending value before fees, taxes, dividends, and trades: {capital * (1 + total_return):,.2f}",
    ])
    st.caption(
        "Answers use Gemini and this summary of your uploaded price history; the uploaded rows are not sent. "
        "Your question and recent chat are sent to Google. This app has no live news feed or brokerage/account connection. "
        "Generated answers can be wrong and are not professional financial advice."
    )
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
        st.caption("Using the Gemini API key configured in the server environment.")
    else:
        with st.expander("Connect Gemini", expanded=True):
            api_key = st.text_input(
                "Google AI Studio API key",
                type="password",
                key="marketlens_gemini_api_key",
            ).strip()
            st.caption("The key is used for this session's Gemini requests. It is not written to the uploaded file.")
    if st.session_state.get("marketlens_advisor_context") != advisor_context:
        st.session_state["marketlens_advisor_context"] = advisor_context
        st.session_state["marketlens_advisor_messages"] = []
    advisor_messages = st.session_state.setdefault("marketlens_advisor_messages", [])
    clear_col, _ = st.columns([1, 5])
    with clear_col:
        if st.button("Clear advisor chat"):
            st.session_state["marketlens_advisor_messages"] = []
            advisor_messages = st.session_state["marketlens_advisor_messages"]
    question = st.chat_input(
        "Ask about this history, returns, or general profit-management concepts",
        max_chars=1500,
        disabled=not api_key,
    )
    if question:
        try:
            with st.spinner("Gemini is preparing an answer…"):
                answer = gemini_advisor_reply(
                    api_key,
                    advisor_context,
                    advisor_messages,
                    question,
                )
        except (requests.RequestException, ValueError, KeyError, TypeError, RuntimeError) as exc:
            st.error(f"Could not get an advisor response: {exc}")
            st.info("Check the Gemini API key and quota, then try again.")
        else:
            advisor_messages.extend([
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ])
            del advisor_messages[:-20]
    for message in advisor_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

elif page == "Price & Returns":
    st.markdown('<div class="section-title">Price and performance history</div>',unsafe_allow_html=True)
    view=st.radio("Measure",["Price","Cumulative return","Daily return"],horizontal=True)
    chart_type=st.radio("Chart type",["Line","Bar","Pie · return split"],horizontal=True)
    values={"Price":price,"Cumulative return":work["Cumulative Return"]*100,"Daily return":work["Return"]*100}[view]
    if chart_type == "Pie · return split":
        returns=work["Return"].dropna()
        gains=float(returns[returns>0].sum())
        losses=float(-returns[returns<0].sum())
        split_labels=[]
        split_values=[]
        if gains>0:
            split_labels.append("Gross positive returns")
            split_values.append(gains)
        if losses>0:
            split_labels.append("Gross negative returns")
            split_values.append(losses)
        if not split_values:
            st.info("A return-split pie chart needs at least one non-zero period return.")
        else:
            f=go.Figure(go.Pie(labels=split_labels,values=split_values,hole=.45,textinfo="label+percent"))
            f.update_layout(template="plotly_dark",height=460,margin=dict(l=10,r=10,t=15,b=10))
            st.plotly_chart(f,use_container_width=True)
            st.caption("Pie slices compare the total magnitude of positive and negative period returns; they do not represent net return or price allocation.")
    else:
        if chart_type == "Bar":
            trace=go.Bar(x=index,y=values,name=view,marker_color="#50b89b")
        else:
            trace=go.Scatter(x=index,y=values,mode="lines",line=dict(color="#2f80ed",width=2),name=view)
        f=go.Figure(trace)
        f.update_layout(template="plotly_dark",height=460,margin=dict(l=10,r=10,t=15,b=10),xaxis_title="Date" if date_col else "Observation",yaxis_title={"Price":"Price","Cumulative return":"Cumulative return (%)","Daily return":"Return (%)"}[view],hovermode="x unified")
        st.plotly_chart(f,use_container_width=True)
    if volume_guess:
        vol_data=pd.to_numeric(work[volume_guess],errors="coerce")
        vf=go.Figure(go.Bar(x=index,y=vol_data,marker_color="#a9bce0",name="Volume")); vf.update_layout(template="plotly_dark",height=240,margin=dict(l=10,r=10,t=10,b=10),yaxis_title="Volume"); st.plotly_chart(vf,use_container_width=True)

elif page == "Profit / Loss":
    st.markdown('<div class="section-title">Hypothetical investment history</div>',unsafe_allow_html=True)
    st.warning("Illustration only: assumes a one-time investment at the first observed price, no fees, taxes, dividends, slippage, or additional trades. This is not your actual account P&L.")
    pnl=float(work["Hypothetical P&L"].iloc[-1])
    a,b,c=st.columns(3); a.metric("Starting capital",f"{capital:,.2f}"); b.metric("Hypothetical ending value",f"{capital+pnl:,.2f}"); c.metric("Hypothetical profit / loss",f"{pnl:+,.2f}",f"{total_return:+.2%}")
    pf=go.Figure(go.Scatter(x=index,y=work["Hypothetical P&L"],mode="lines",line=dict(color="#1b9b76" if pnl>=0 else "#db5a63",width=2.5),fill="tozeroy",fillcolor="rgba(27,155,118,.08)")); pf.add_hline(y=0,line_dash="dash",line_color="#8996a8"); pf.update_layout(template="plotly_dark",height=400,yaxis_title="Unrealized P&L",xaxis_title="Date" if date_col else "Observation",margin=dict(l=10,r=10,t=15,b=10),hovermode="x unified"); st.plotly_chart(pf,use_container_width=True)
    history=pd.DataFrame({"Date/Observation": index,"Price":price,"Period return":work["Return"],"Cumulative return":work["Cumulative Return"],"Hypothetical P&L":work["Hypothetical P&L"]})
    st.dataframe(history.tail(25).style.format({"Price":"{:,.2f}","Period return":"{:+.2%}","Cumulative return":"{:+.2%}","Hypothetical P&L":"{:+,.2f}"}),use_container_width=True,hide_index=True)

elif page == "Forecast":
    st.markdown('<div class="section-title">Trend projection</div>',unsafe_allow_html=True)
    st.warning("This is a simple linear regression on historical prices, projected forward mechanically. It does not model market drivers, uncertainty, events, or changing regimes and must not be used as a trading recommendation.")
    horizon=st.slider("Projection horizon (observations)",min_value=5,max_value=90,value=30,step=5)
    n=len(price); x=np.arange(n,dtype=float); slope,intercept=np.polyfit(x,price.to_numpy(),1) if n>1 else (0.0,last)
    fitted=intercept+slope*x; future_x=np.arange(n-1,n+horizon,dtype=float); future_y=intercept+slope*future_x
    residual=price.to_numpy()-fitted; rmse=float(np.sqrt(np.mean(residual**2))) if n>2 else 0.0
    if date_col:
        dates=pd.to_datetime(work[date_col]); freq=pd.infer_freq(dates.tail(min(len(dates),30))) if len(dates)>=3 else None
        if freq:
            future_dates=pd.date_range(dates.iloc[-1],periods=horizon+1,freq=freq)[1:]
        else:
            delta=dates.diff().dropna().median() if len(dates)>1 else pd.Timedelta(days=1)
            future_dates=pd.DatetimeIndex([dates.iloc[-1]+delta*i for i in range(1,horizon+1)])
        hist_x=dates; pred_x=pd.DatetimeIndex([dates.iloc[-1]]).append(future_dates)
        labels=dates
    else:
        labels=np.arange(1,n+1); hist_x=labels; pred_x=np.arange(n,n+horizon+1)
    fc=go.Figure(); fc.add_trace(go.Scatter(x=hist_x,y=price,mode="lines",name="Historical price",line=dict(color="#2f80ed",width=2))); fc.add_trace(go.Scatter(x=pred_x,y=future_y,mode="lines",name="Linear trend projection",line=dict(color="#ed9b40",width=2,dash="dash"))); fc.add_trace(go.Scatter(x=pred_x,y=future_y+1.96*rmse,mode="lines",line=dict(width=0),showlegend=False,hoverinfo="skip")); fc.add_trace(go.Scatter(x=pred_x,y=future_y-1.96*rmse,mode="lines",line=dict(width=0),fill="tonexty",fillcolor="rgba(237,155,64,.12)",name="Residual band (±1.96 RMSE)",hoverinfo="skip")); fc.update_layout(template="plotly_dark",height=440,hovermode="x unified",margin=dict(l=10,r=10,t=15,b=10),yaxis_title="Price",xaxis_title="Date" if date_col else "Observation"); st.plotly_chart(fc,use_container_width=True)
    estimate=float(intercept+slope*(n+horizon-1)); st.metric(f"Trend estimate at horizon ({horizon} observations)",f"{estimate:,.2f}",f"{estimate/last-1:+.2%} vs latest")
    st.caption(f"The shaded residual band describes historical fit error, not a statistically calibrated prediction interval. Inferred daily/date spacing follows the uploaded observations where possible.")

else:
    st.markdown('<div class="section-title">Dataset explorer</div>',unsafe_allow_html=True)
    t1,t2,t3=st.tabs(["Preview","Quality","Summary"])
    with t1:
        st.dataframe(data,use_container_width=True,height=420)
        st.download_button("Download cleaned price history (CSV)",work.to_csv(index=False).encode("utf-8"),file_name="marketlens_cleaned_history.csv",mime="text/csv")
    with t2:
        quality=pd.DataFrame({"Column":data.columns,"Type":[str(t) for t in data.dtypes],"Missing values":data.isna().sum().values,"Missing %":(data.isna().mean()*100).round(2).values,"Unique values":data.nunique(dropna=True).values})
        st.dataframe(quality,use_container_width=True,hide_index=True)
        st.metric("Total missing cells",f"{int(data.isna().sum().sum()):,}")
    with t3:
        st.dataframe(data.describe(include="all").transpose(),use_container_width=True)

st.markdown("---")
st.caption("MarketLens is an educational analysis tool. Historical performance does not guarantee future results. No investment, tax, or financial advice is provided.")