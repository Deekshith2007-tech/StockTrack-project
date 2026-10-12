# MarketLens

MarketLens is a Streamlit dashboard for exploring uploaded stock-market data. It includes price and return charts, hypothetical profit/loss, a simple trend projection, a dataset explorer, live Crypto.com market data, and an optional Gemini-powered educational advisor.

## Requirements

- Python 3.10 or newer
- Dependencies listed in `requirements.txt`

## Run locally

From the project directory, create and activate a virtual environment, install dependencies, and start the app:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Upload a CSV or Excel `.xlsx` file in the main page. A date column and a closing-price column (such as `Date` and `Close`) are recommended.

## Optional Gemini advisor

The Overview advisor requires a Gemini API key. Set `GEMINI_API_KEY` in the environment before starting Streamlit:

```powershell
$env:GEMINI_API_KEY = "your-gemini-api-key"
python -m streamlit run app.py
```

Alternatively, enter a key in the advisor's **Connect Gemini** field for the current session. Requests send the user's question, recent conversation, and a calculated summary of the uploaded price history to Google's Gemini API; raw uploaded rows are not sent. Do not commit API keys to source control.

The advisor provides generated educational information, not personalized or professional financial advice. The live Crypto.com page also requires an internet connection to reach Crypto.com Exchange.
