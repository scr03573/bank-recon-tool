import React, { useState, useEffect } from 'react';
import {
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Search,
  Building2,
  DollarSign,
  Activity,
  Percent
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  AreaChart, Area
} from 'recharts';
import { getMarketSnapshot, getEconomicIndicators, getStockQuote, validateVendor } from '../api';

function IndicatorCard({ name, value, unit, description, trend }) {
  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-slate-500">{name}</span>
        {trend && (
          trend > 0 ? (
            <TrendingUp className="text-green-500" size={16} />
          ) : (
            <TrendingDown className="text-red-500" size={16} />
          )
        )}
      </div>
      <p className="text-2xl font-bold text-slate-900">
        {value !== null && value !== undefined ? value.toFixed(2) : 'N/A'}
        <span className="text-sm font-normal text-slate-500 ml-1">{unit}</span>
      </p>
      {description && <p className="text-xs text-slate-400 mt-1">{description}</p>}
    </div>
  );
}

function StockQuoteDisplay({ quote }) {
  if (!quote) return null;

  const isPositive = quote.change_percent >= 0;

  return (
    <div className="bg-white rounded-xl shadow-sm p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-2xl font-bold text-slate-900">{quote.ticker}</h3>
          <p className="text-sm text-slate-500">Source: {quote.source}</p>
        </div>
        <div className={`text-right ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
          <p className="text-3xl font-bold">${quote.price.toFixed(2)}</p>
          <p className="text-sm flex items-center justify-end gap-1">
            {isPositive ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
            {isPositive ? '+' : ''}{quote.change.toFixed(2)} ({quote.change_percent.toFixed(2)}%)
          </p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-slate-500">Volume</span>
          <p className="font-medium">{quote.volume.toLocaleString()}</p>
        </div>
        <div>
          <span className="text-slate-500">Change</span>
          <p className={`font-medium ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
            {isPositive ? '+' : ''}{quote.change_percent.toFixed(2)}%
          </p>
        </div>
      </div>
    </div>
  );
}

function VendorValidationResult({ validation }) {
  if (!validation) return null;

  return (
    <div className="bg-white rounded-xl shadow-sm p-6">
      <div className="flex items-center gap-3 mb-4">
        <div className={`p-2 rounded-lg ${validation.is_public ? 'bg-green-100' : 'bg-slate-100'}`}>
          <Building2 className={validation.is_public ? 'text-green-600' : 'text-slate-400'} size={24} />
        </div>
        <div>
          <h3 className="font-semibold text-slate-900">{validation.vendor_name}</h3>
          <p className="text-sm text-slate-500">
            {validation.is_public ? 'Publicly Traded Company' : 'Not a Public Company'}
          </p>
        </div>
      </div>

      {validation.is_public && (
        <div className="space-y-3">
          <div className="flex justify-between py-2 border-b border-slate-100">
            <span className="text-slate-500">Ticker Symbol</span>
            <span className="font-semibold text-slate-900">{validation.ticker}</span>
          </div>
          {validation.company_name && (
            <div className="flex justify-between py-2 border-b border-slate-100">
              <span className="text-slate-500">Company Name</span>
              <span className="font-medium text-slate-900">{validation.company_name}</span>
            </div>
          )}
          <div className="flex justify-between py-2 border-b border-slate-100">
            <span className="text-slate-500">Status</span>
            <span className={`font-medium ${validation.is_active ? 'text-green-600' : 'text-slate-400'}`}>
              {validation.is_active ? 'Active' : 'Inactive'}
            </span>
          </div>
          {validation.price && (
            <div className="flex justify-between py-2">
              <span className="text-slate-500">Current Price</span>
              <span className="font-semibold text-slate-900">${validation.price.toFixed(2)}</span>
            </div>
          )}
        </div>
      )}

      {!validation.is_public && (
        <div className="mt-4 p-3 bg-slate-50 rounded-lg text-sm text-slate-600">
          This vendor is not recognized as a publicly traded company. Economic validation based on stock data is not available.
        </div>
      )}
    </div>
  );
}

export default function MarketData() {
  const [loading, setLoading] = useState(true);
  const [snapshot, setSnapshot] = useState(null);
  const [indicators, setIndicators] = useState({});
  const [error, setError] = useState(null);

  // Stock lookup
  const [ticker, setTicker] = useState('');
  const [quote, setQuote] = useState(null);
  const [quoteLoading, setQuoteLoading] = useState(false);
  const [quoteError, setQuoteError] = useState(null);

  // Vendor validation
  const [vendorName, setVendorName] = useState('');
  const [validation, setValidation] = useState(null);
  const [validationLoading, setValidationLoading] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [snapshotRes, indicatorsRes] = await Promise.all([
        getMarketSnapshot(),
        getEconomicIndicators().catch(() => ({ data: {} }))
      ]);
      setSnapshot(snapshotRes.data);
      setIndicators(indicatorsRes.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load market data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleLookupStock = async (e) => {
    e.preventDefault();
    if (!ticker.trim()) return;

    setQuoteLoading(true);
    setQuoteError(null);
    setQuote(null);
    try {
      const res = await getStockQuote(ticker.trim().toUpperCase());
      setQuote(res.data);
    } catch (err) {
      setQuoteError(err.response?.data?.detail || 'Failed to fetch quote');
    } finally {
      setQuoteLoading(false);
    }
  };

  const handleValidateVendor = async (e) => {
    e.preventDefault();
    if (!vendorName.trim()) return;

    setValidationLoading(true);
    setValidation(null);
    try {
      const res = await validateVendor(vendorName.trim());
      setValidation(res.data);
    } catch (err) {
      console.error('Validation failed:', err);
    } finally {
      setValidationLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Market Data</h1>
          <p className="text-slate-500">Real-time market and economic indicators</p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 flex items-center gap-2"
        >
          <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Market Snapshot */}
      {snapshot && (
        <div className="bg-gradient-to-r from-blue-600 to-indigo-700 rounded-xl shadow-lg p-6 text-white">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-xl font-semibold">Market Overview</h2>
              <p className="text-blue-200 text-sm">As of {new Date(snapshot.as_of).toLocaleString()}</p>
            </div>
            <span className={`px-3 py-1 rounded-full text-sm font-medium ${
              snapshot.market_status === 'NORMAL' ? 'bg-green-500/20 text-green-200' :
              snapshot.market_status === 'ELEVATED' ? 'bg-yellow-500/20 text-yellow-200' :
              'bg-red-500/20 text-red-200'
            }`}>
              {snapshot.market_status}
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div>
              <p className="text-blue-200 text-sm">S&P 500</p>
              <p className="text-2xl font-bold">
                {snapshot.sp500 ? `$${snapshot.sp500.toLocaleString()}` : 'N/A'}
              </p>
              {snapshot.sp500_change !== null && (
                <p className={`text-sm ${snapshot.sp500_change >= 0 ? 'text-green-300' : 'text-red-300'}`}>
                  {snapshot.sp500_change >= 0 ? '+' : ''}{snapshot.sp500_change?.toFixed(2)}%
                </p>
              )}
            </div>
            <div>
              <p className="text-blue-200 text-sm">VIX</p>
              <p className="text-2xl font-bold">{snapshot.vix?.toFixed(1) || 'N/A'}</p>
              <p className="text-sm text-blue-200">Volatility Index</p>
            </div>
            <div>
              <p className="text-blue-200 text-sm">Fed Funds Rate</p>
              <p className="text-2xl font-bold">{snapshot.fed_funds_rate?.toFixed(2) || 'N/A'}%</p>
              <p className="text-sm text-blue-200">Interest Rate</p>
            </div>
            <div>
              <p className="text-blue-200 text-sm">Yield Curve</p>
              <p className="text-2xl font-bold">{snapshot.yield_curve_spread?.toFixed(2) || 'N/A'}%</p>
              <p className={`text-sm ${snapshot.yield_curve_inverted ? 'text-yellow-300' : 'text-blue-200'}`}>
                {snapshot.yield_curve_inverted ? 'Inverted' : '10Y-2Y Spread'}
              </p>
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-white/20 text-sm text-blue-200">
            Data Sources: {snapshot.data_sources?.join(', ') || 'N/A'}
          </div>
        </div>
      )}

      {/* Economic Indicators Grid */}
      <div>
        <h3 className="text-lg font-semibold text-slate-900 mb-4">Economic Indicators (FRED)</h3>
        {loading ? (
          <div className="flex justify-center py-8">
            <RefreshCw className="animate-spin text-slate-400" size={32} />
          </div>
        ) : Object.keys(indicators).length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Object.entries(indicators).map(([key, indicator]) => (
              <IndicatorCard
                key={key}
                name={indicator.name}
                value={indicator.value}
                unit={indicator.unit}
                description={indicator.date ? `As of ${indicator.date}` : null}
              />
            ))}
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm p-8 text-center text-slate-400">
            No economic indicators available. Ensure FRED API is configured.
          </div>
        )}
      </div>

      {/* Tools Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Stock Lookup */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h3 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <Activity size={20} />
            Stock Quote Lookup
          </h3>
          <form onSubmit={handleLookupStock} className="flex gap-2 mb-4">
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="Enter ticker (e.g., MSFT)"
              className="flex-1 px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <button
              type="submit"
              disabled={quoteLoading || !ticker.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
            >
              {quoteLoading ? <RefreshCw className="animate-spin" size={18} /> : <Search size={18} />}
              Lookup
            </button>
          </form>

          {quoteError && (
            <div className="text-red-600 text-sm mb-4">{quoteError}</div>
          )}

          {quote && <StockQuoteDisplay quote={quote} />}

          <div className="mt-4 text-xs text-slate-400">
            Try: AAPL, MSFT, GOOGL, AMZN, META, TSLA
          </div>
        </div>

        {/* Vendor Validation */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h3 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <Building2 size={20} />
            Vendor Validation
          </h3>
          <form onSubmit={handleValidateVendor} className="flex gap-2 mb-4">
            <input
              type="text"
              value={vendorName}
              onChange={(e) => setVendorName(e.target.value)}
              placeholder="Enter vendor name (e.g., Microsoft)"
              className="flex-1 px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <button
              type="submit"
              disabled={validationLoading || !vendorName.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
            >
              {validationLoading ? <RefreshCw className="animate-spin" size={18} /> : <Search size={18} />}
              Validate
            </button>
          </form>

          {validation && <VendorValidationResult validation={validation} />}

          <div className="mt-4 text-xs text-slate-400">
            Try: Microsoft, Amazon, FedEx, Home Depot, Walmart
          </div>
        </div>
      </div>

      {/* Data Sources Info */}
      <div className="bg-slate-50 rounded-xl p-6">
        <h3 className="font-semibold text-slate-900 mb-3">Data Sources</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div className="bg-white rounded-lg p-4">
            <div className="font-medium text-slate-900 mb-1">yfinance</div>
            <p className="text-slate-500">Free stock quotes, indices, and historical data</p>
            <span className="inline-block mt-2 px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded">Default</span>
          </div>
          <div className="bg-white rounded-lg p-4">
            <div className="font-medium text-slate-900 mb-1">FRED</div>
            <p className="text-slate-500">Federal Reserve economic data (rates, inflation, unemployment)</p>
            <span className="inline-block mt-2 px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded">Free API</span>
          </div>
          <div className="bg-white rounded-lg p-4">
            <div className="font-medium text-slate-900 mb-1">Intrinio</div>
            <p className="text-slate-500">Premium financial data and company fundamentals</p>
            <span className="inline-block mt-2 px-2 py-0.5 bg-purple-100 text-purple-700 text-xs rounded">Premium</span>
          </div>
        </div>
      </div>
    </div>
  );
}
