import React, { useState, useEffect } from 'react';
import {
  Settings,
  Database,
  Key,
  Sliders,
  RefreshCw,
  CheckCircle,
  XCircle,
  ExternalLink
} from 'lucide-react';
import { getStatus } from '../api';

function StatusBadge({ configured, label }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-slate-100 last:border-0">
      <span className="text-slate-700">{label}</span>
      <span className={`flex items-center gap-2 ${configured ? 'text-green-600' : 'text-slate-400'}`}>
        {configured ? (
          <>
            <CheckCircle size={16} />
            Connected
          </>
        ) : (
          <>
            <XCircle size={16} />
            Not configured
          </>
        )}
      </span>
    </div>
  );
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  const fetchStatus = async () => {
    setLoading(true);
    try {
      const res = await getStatus();
      setStatus(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
        <p className="text-slate-500">System configuration and status</p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12">
          <RefreshCw className="animate-spin text-slate-400" size={32} />
        </div>
      ) : status && (
        <div className="space-y-6">
          {/* API Connections */}
          <div className="bg-white rounded-xl shadow-sm">
            <div className="p-4 border-b border-slate-200 flex items-center gap-3">
              <div className="p-2 bg-blue-100 rounded-lg">
                <Key className="text-blue-600" size={20} />
              </div>
              <div>
                <h2 className="font-semibold text-slate-900">API Connections</h2>
                <p className="text-sm text-slate-500">External service integrations</p>
              </div>
            </div>
            <div className="p-4">
              <StatusBadge configured={status.intacct_configured} label="Sage Intacct" />
              <StatusBadge configured={status.fred_configured} label="FRED API" />
              <StatusBadge configured={status.intrinio_configured} label="Intrinio API" />
            </div>
          </div>

          {/* Matching Configuration */}
          <div className="bg-white rounded-xl shadow-sm">
            <div className="p-4 border-b border-slate-200 flex items-center gap-3">
              <div className="p-2 bg-purple-100 rounded-lg">
                <Sliders className="text-purple-600" size={20} />
              </div>
              <div>
                <h2 className="font-semibold text-slate-900">Matching Configuration</h2>
                <p className="text-sm text-slate-500">Transaction matching parameters</p>
              </div>
            </div>
            <div className="p-4 space-y-4">
              <div className="flex items-center justify-between py-2">
                <div>
                  <p className="font-medium text-slate-700">Fuzzy Match Threshold</p>
                  <p className="text-sm text-slate-500">Minimum similarity score for vendor name matching</p>
                </div>
                <span className="text-xl font-semibold text-slate-900">{status.fuzzy_threshold}%</span>
              </div>
              <div className="flex items-center justify-between py-2">
                <div>
                  <p className="font-medium text-slate-700">Date Tolerance</p>
                  <p className="text-sm text-slate-500">Maximum days difference for date matching</p>
                </div>
                <span className="text-xl font-semibold text-slate-900">{status.date_tolerance_days} days</span>
              </div>
              <div className="flex items-center justify-between py-2">
                <div>
                  <p className="font-medium text-slate-700">Amount Tolerance</p>
                  <p className="text-sm text-slate-500">Maximum percentage difference for amount matching</p>
                </div>
                <span className="text-xl font-semibold text-slate-900">{(status.amount_tolerance_percent * 100).toFixed(1)}%</span>
              </div>
            </div>
          </div>

          {/* Data Priority */}
          <div className="bg-white rounded-xl shadow-sm">
            <div className="p-4 border-b border-slate-200 flex items-center gap-3">
              <div className="p-2 bg-green-100 rounded-lg">
                <Database className="text-green-600" size={20} />
              </div>
              <div>
                <h2 className="font-semibold text-slate-900">Market Data Settings</h2>
                <p className="text-sm text-slate-500">Data source priority and caching</p>
              </div>
            </div>
            <div className="p-4">
              <div className="flex items-center justify-between py-2">
                <div>
                  <p className="font-medium text-slate-700">Data Priority</p>
                  <p className="text-sm text-slate-500">Order of preference for market data sources</p>
                </div>
                <span className="px-3 py-1 bg-slate-100 text-slate-700 rounded-lg font-mono text-sm">
                  {status.market_data_priority}
                </span>
              </div>
            </div>
          </div>

          {/* Configuration Help */}
          <div className="bg-slate-50 rounded-xl p-6">
            <h3 className="font-semibold text-slate-900 mb-3">Configuration</h3>
            <p className="text-sm text-slate-600 mb-4">
              Settings are configured via environment variables in the <code className="bg-slate-200 px-1 rounded">.env</code> file.
            </p>
            <div className="bg-white rounded-lg p-4 font-mono text-sm overflow-x-auto">
              <pre className="text-slate-600">
{`# Sage Intacct
INTACCT_SENDER_ID=your_sender_id
INTACCT_SENDER_PASSWORD=your_password
INTACCT_USER_ID=your_user_id
INTACCT_USER_PASSWORD=your_password
INTACCT_COMPANY_ID=your_company_id

# Market Data APIs
FRED_API_KEY=your_fred_key
INTRINIO_API_KEY=your_intrinio_key

# Market Data Priority
# Options: intrinio_first, yfinance_first, best_available
MARKET_DATA_PRIORITY=yfinance_first

# Matching Thresholds
FUZZY_MATCH_THRESHOLD=85
DATE_TOLERANCE_DAYS=5
AMOUNT_TOLERANCE_PERCENT=0.01`}
              </pre>
            </div>

            <div className="mt-4 flex gap-4">
              <a
                href="https://fred.stlouisfed.org/docs/api/api_key.html"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:text-blue-700 text-sm flex items-center gap-1"
              >
                Get FRED API Key <ExternalLink size={14} />
              </a>
              <a
                href="https://intrinio.com/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:text-blue-700 text-sm flex items-center gap-1"
              >
                Get Intrinio API Key <ExternalLink size={14} />
              </a>
            </div>
          </div>

          {/* About */}
          <div className="bg-white rounded-xl shadow-sm p-6">
            <h3 className="font-semibold text-slate-900 mb-3">About</h3>
            <div className="space-y-2 text-sm text-slate-600">
              <p><span className="font-medium">Application:</span> Bank Reconciliation Tool</p>
              <p><span className="font-medium">Version:</span> 1.0.0</p>
              <p><span className="font-medium">Purpose:</span> Automated bank reconciliation with Sage Intacct integration and market data validation</p>
            </div>
            <div className="mt-4 pt-4 border-t border-slate-100">
              <a
                href="https://github.com/scr03573/bank-recon-tool"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:text-blue-700 text-sm flex items-center gap-1"
              >
                View on GitHub <ExternalLink size={14} />
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
