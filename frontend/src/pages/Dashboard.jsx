import React, { useState, useEffect } from 'react';
import {
  CheckCircle,
  AlertTriangle,
  Clock,
  DollarSign,
  TrendingUp,
  TrendingDown,
  Activity,
  RefreshCw,
  Play
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line
} from 'recharts';
import { getStatus, getMarketSnapshot, getReconciliationHistory, runDemoReconciliation } from '../api';

const COLORS = ['#10b981', '#f59e0b', '#ef4444', '#6366f1'];

function StatCard({ icon: Icon, label, value, subValue, color = 'blue' }) {
  const colorClasses = {
    blue: 'bg-blue-500',
    green: 'bg-green-500',
    yellow: 'bg-yellow-500',
    red: 'bg-red-500',
    purple: 'bg-purple-500'
  };

  return (
    <div className="bg-white rounded-xl shadow-sm p-6">
      <div className="flex items-center">
        <div className={`${colorClasses[color]} p-3 rounded-lg`}>
          <Icon className="text-white" size={24} />
        </div>
        <div className="ml-4">
          <p className="text-sm text-slate-500">{label}</p>
          <p className="text-2xl font-bold text-slate-900">{value}</p>
          {subValue && <p className="text-xs text-slate-400">{subValue}</p>}
        </div>
      </div>
    </div>
  );
}

function MarketIndicator({ label, value, change, unit = '' }) {
  const isPositive = change >= 0;
  return (
    <div className="flex items-center justify-between py-3 border-b border-slate-100 last:border-0">
      <span className="text-slate-600">{label}</span>
      <div className="text-right">
        <span className="font-semibold text-slate-900">{value}{unit}</span>
        {change !== undefined && (
          <span className={`ml-2 text-sm ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
            {isPositive ? '+' : ''}{change}%
          </span>
        )}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState(null);
  const [market, setMarket] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRes, marketRes, historyRes] = await Promise.all([
        getStatus(),
        getMarketSnapshot().catch(() => ({ data: null })),
        getReconciliationHistory(1, 5)
      ]);
      setStatus(statusRes.data);
      setMarket(marketRes.data);
      setHistory(historyRes.data?.items || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleRunDemo = async () => {
    setRunning(true);
    try {
      await runDemoReconciliation();
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to run demo');
    } finally {
      setRunning(false);
    }
  };

  const latestRun = history[0];

  const matchData = history.slice(0, 5).reverse().map((h, i) => ({
    name: `Run ${i + 1}`,
    matched: h.matched_count,
    exceptions: h.exception_count
  }));

  const pieData = latestRun ? [
    { name: 'Matched', value: latestRun.matched_count },
    { name: 'Unmatched', value: latestRun.total_bank_transactions - latestRun.matched_count }
  ] : [];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="animate-spin text-blue-500" size={40} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
          <p className="text-slate-500">Bank reconciliation overview</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={fetchData}
            className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 flex items-center gap-2"
          >
            <RefreshCw size={18} />
            Refresh
          </button>
          <button
            onClick={handleRunDemo}
            disabled={running}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2 disabled:opacity-50"
          >
            {running ? <RefreshCw className="animate-spin" size={18} /> : <Play size={18} />}
            Run Demo
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          icon={CheckCircle}
          label="Match Rate"
          value={latestRun ? `${(latestRun.match_rate * 100).toFixed(1)}%` : 'N/A'}
          subValue={latestRun ? `${latestRun.matched_count} matched` : 'No runs yet'}
          color="green"
        />
        <StatCard
          icon={AlertTriangle}
          label="Exceptions"
          value={latestRun?.exception_count || 0}
          subValue="Requires review"
          color="yellow"
        />
        <StatCard
          icon={DollarSign}
          label="Total Matched"
          value={latestRun ? `$${(latestRun.total_matched_amount / 1000).toFixed(0)}K` : '$0'}
          subValue="This period"
          color="blue"
        />
        <StatCard
          icon={Clock}
          label="Total Runs"
          value={history.length}
          subValue="Reconciliations"
          color="purple"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Match History Chart */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h3 className="text-lg font-semibold text-slate-900 mb-4">Match History</h3>
          {matchData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={matchData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="name" stroke="#94a3b8" />
                <YAxis stroke="#94a3b8" />
                <Tooltip />
                <Bar dataKey="matched" fill="#10b981" name="Matched" />
                <Bar dataKey="exceptions" fill="#f59e0b" name="Exceptions" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-64 flex items-center justify-center text-slate-400">
              No data available. Run a reconciliation to see results.
            </div>
          )}
        </div>

        {/* Match Distribution */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h3 className="text-lg font-semibold text-slate-900 mb-4">Match Distribution</h3>
          {pieData.length > 0 && pieData[0].value > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-64 flex items-center justify-center text-slate-400">
              No data available
            </div>
          )}
        </div>
      </div>

      {/* Market Data & Status Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Market Snapshot */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-slate-900">Market Snapshot</h3>
            {market?.market_status && (
              <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                market.market_status === 'NORMAL' ? 'bg-green-100 text-green-700' :
                market.market_status === 'ELEVATED' ? 'bg-yellow-100 text-yellow-700' :
                'bg-red-100 text-red-700'
              }`}>
                {market.market_status}
              </span>
            )}
          </div>
          {market ? (
            <div>
              <MarketIndicator
                label="S&P 500"
                value={market.sp500 ? `$${market.sp500.toLocaleString()}` : 'N/A'}
                change={market.sp500_change}
              />
              <MarketIndicator
                label="VIX (Volatility)"
                value={market.vix?.toFixed(1) || 'N/A'}
              />
              <MarketIndicator
                label="Fed Funds Rate"
                value={market.fed_funds_rate?.toFixed(2) || 'N/A'}
                unit="%"
              />
              <MarketIndicator
                label="10Y Treasury"
                value={market.treasury_10y?.toFixed(2) || 'N/A'}
                unit="%"
              />
              <MarketIndicator
                label="Yield Curve"
                value={market.yield_curve_spread?.toFixed(2) || 'N/A'}
                unit="%"
              />
              {market.yield_curve_inverted && (
                <div className="mt-3 p-2 bg-yellow-50 border border-yellow-200 rounded text-yellow-700 text-sm">
                  Warning: Yield curve is inverted
                </div>
              )}
              <div className="mt-4 text-xs text-slate-400">
                Sources: {market.data_sources?.join(', ') || 'N/A'}
              </div>
            </div>
          ) : (
            <div className="text-slate-400 py-8 text-center">
              Market data unavailable
            </div>
          )}
        </div>

        {/* System Status */}
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h3 className="text-lg font-semibold text-slate-900 mb-4">System Status</h3>
          {status ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between py-2">
                <span className="text-slate-600">Sage Intacct</span>
                <span className={`flex items-center ${status.intacct_configured ? 'text-green-500' : 'text-slate-400'}`}>
                  <span className={`w-2 h-2 rounded-full mr-2 ${status.intacct_configured ? 'bg-green-500' : 'bg-slate-300'}`} />
                  {status.intacct_configured ? 'Connected' : 'Not configured'}
                </span>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-slate-600">FRED API</span>
                <span className={`flex items-center ${status.fred_configured ? 'text-green-500' : 'text-slate-400'}`}>
                  <span className={`w-2 h-2 rounded-full mr-2 ${status.fred_configured ? 'bg-green-500' : 'bg-slate-300'}`} />
                  {status.fred_configured ? 'Connected' : 'Not configured'}
                </span>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-slate-600">Intrinio API</span>
                <span className={`flex items-center ${status.intrinio_configured ? 'text-green-500' : 'text-slate-400'}`}>
                  <span className={`w-2 h-2 rounded-full mr-2 ${status.intrinio_configured ? 'bg-green-500' : 'bg-slate-300'}`} />
                  {status.intrinio_configured ? 'Connected' : 'Not configured'}
                </span>
              </div>
              <hr className="my-2" />
              <div className="text-sm text-slate-500 space-y-1">
                <p>Data Priority: <span className="font-medium text-slate-700">{status.market_data_priority}</span></p>
                <p>Fuzzy Threshold: <span className="font-medium text-slate-700">{status.fuzzy_threshold}%</span></p>
                <p>Date Tolerance: <span className="font-medium text-slate-700">{status.date_tolerance_days} days</span></p>
              </div>
            </div>
          ) : (
            <div className="text-slate-400 py-8 text-center">
              Status unavailable
            </div>
          )}
        </div>
      </div>

      {/* Recent Runs */}
      <div className="bg-white rounded-xl shadow-sm p-6">
        <h3 className="text-lg font-semibold text-slate-900 mb-4">Recent Reconciliations</h3>
        {history.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-slate-500 text-sm border-b">
                  <th className="pb-3 font-medium">Run ID</th>
                  <th className="pb-3 font-medium">Date Range</th>
                  <th className="pb-3 font-medium">Transactions</th>
                  <th className="pb-3 font-medium">Match Rate</th>
                  <th className="pb-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {history.map((run) => (
                  <tr key={run.run_id} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="py-3 text-sm font-mono text-slate-600">{run.run_id.slice(0, 8)}...</td>
                    <td className="py-3 text-sm text-slate-600">
                      {run.start_date} to {run.end_date}
                    </td>
                    <td className="py-3 text-sm text-slate-600">
                      {run.total_bank_transactions} bank / {run.total_ap_transactions} AP
                    </td>
                    <td className="py-3">
                      <span className={`text-sm font-medium ${
                        run.match_rate >= 0.9 ? 'text-green-600' :
                        run.match_rate >= 0.7 ? 'text-yellow-600' : 'text-red-600'
                      }`}>
                        {(run.match_rate * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-3">
                      <span className={`px-2 py-1 text-xs rounded-full ${
                        run.status === 'completed' ? 'bg-green-100 text-green-700' :
                        run.status === 'running' ? 'bg-blue-100 text-blue-700' :
                        'bg-slate-100 text-slate-700'
                      }`}>
                        {run.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-slate-400 py-8 text-center">
            No reconciliation runs yet. Click "Run Demo" to get started.
          </div>
        )}
      </div>
    </div>
  );
}
