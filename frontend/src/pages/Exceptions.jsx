import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle,
  RefreshCw,
  Filter,
  X
} from 'lucide-react';
import { getExceptions, resolveException, getReconciliationHistory } from '../api';

const SEVERITY_CONFIG = {
  high: { icon: AlertCircle, color: 'red', bg: 'bg-red-100', text: 'text-red-700', border: 'border-red-200' },
  medium: { icon: AlertTriangle, color: 'yellow', bg: 'bg-yellow-100', text: 'text-yellow-700', border: 'border-yellow-200' },
  low: { icon: Info, color: 'blue', bg: 'bg-blue-100', text: 'text-blue-700', border: 'border-blue-200' }
};

const EXCEPTION_TYPES = [
  { value: '', label: 'All Types' },
  { value: 'missing_ap_record', label: 'Missing AP Record' },
  { value: 'missing_bank_record', label: 'Missing Bank Record' },
  { value: 'duplicate_payment', label: 'Duplicate Payment' },
  { value: 'amount_mismatch', label: 'Amount Mismatch' },
  { value: 'stale_check', label: 'Stale Check' }
];

function ExceptionCard({ exception, onResolve }) {
  const [showResolve, setShowResolve] = useState(false);
  const [notes, setNotes] = useState('');
  const [resolving, setResolving] = useState(false);

  const severity = SEVERITY_CONFIG[exception.severity] || SEVERITY_CONFIG.medium;
  const Icon = severity.icon;

  const handleResolve = async () => {
    if (!notes.trim()) return;
    setResolving(true);
    try {
      await resolveException(exception.exception_id, notes);
      onResolve();
      setShowResolve(false);
      setNotes('');
    } catch (err) {
      console.error('Failed to resolve:', err);
    } finally {
      setResolving(false);
    }
  };

  return (
    <div className={`bg-white rounded-xl shadow-sm border-l-4 ${severity.border} overflow-hidden`}>
      <div className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3">
            <div className={`p-2 rounded-lg ${severity.bg}`}>
              <Icon className={severity.text} size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-slate-900">
                  {exception.exception_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </h3>
                <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${severity.bg} ${severity.text}`}>
                  {exception.severity}
                </span>
              </div>
              <p className="text-sm text-slate-600 mt-1">{exception.description}</p>
            </div>
          </div>
          {exception.is_resolved ? (
            <span className="flex items-center gap-1 text-green-600 text-sm">
              <CheckCircle size={16} />
              Resolved
            </span>
          ) : (
            <button
              onClick={() => setShowResolve(!showResolve)}
              className="text-sm text-blue-600 hover:text-blue-700"
            >
              Resolve
            </button>
          )}
        </div>

        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-slate-500">Transaction ID</span>
            <p className="font-medium text-slate-900 font-mono text-xs">{exception.transaction_id || 'N/A'}</p>
          </div>
          <div>
            <span className="text-slate-500">Date</span>
            <p className="font-medium text-slate-900">{exception.transaction_date || 'N/A'}</p>
          </div>
          <div>
            <span className="text-slate-500">Amount</span>
            <p className="font-medium text-slate-900">
              ${Math.abs(exception.amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </p>
          </div>
          <div>
            <span className="text-slate-500">Suggested Action</span>
            <p className="font-medium text-slate-900">{exception.suggested_action || 'Review manually'}</p>
          </div>
        </div>

        {exception.resolution_notes && (
          <div className="mt-4 p-3 bg-green-50 rounded-lg">
            <p className="text-sm text-green-700">
              <span className="font-medium">Resolution:</span> {exception.resolution_notes}
            </p>
          </div>
        )}
      </div>

      {showResolve && !exception.is_resolved && (
        <div className="px-4 pb-4 pt-2 border-t border-slate-100">
          <label className="block text-sm font-medium text-slate-700 mb-2">Resolution Notes</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Enter resolution details..."
            className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            rows={2}
          />
          <div className="flex gap-2 mt-2">
            <button
              onClick={handleResolve}
              disabled={!notes.trim() || resolving}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 text-sm"
            >
              {resolving ? 'Resolving...' : 'Mark Resolved'}
            </button>
            <button
              onClick={() => setShowResolve(false)}
              className="px-4 py-2 text-slate-600 hover:text-slate-800 text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Exceptions() {
  const [loading, setLoading] = useState(true);
  const [exceptions, setExceptions] = useState([]);
  const [history, setHistory] = useState([]);
  const [selectedRun, setSelectedRun] = useState('');
  const [filterType, setFilterType] = useState('');
  const [unresolvedOnly, setUnresolvedOnly] = useState(false);
  const [error, setError] = useState(null);

  const fetchHistory = async () => {
    try {
      const res = await getReconciliationHistory(10);
      setHistory(res.data);
      if (res.data.length > 0) {
        setSelectedRun(res.data[0].run_id);
      }
    } catch (err) {
      console.error('Failed to load history:', err);
    }
  };

  const fetchExceptions = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getExceptions(
        selectedRun || null,
        filterType || null,
        unresolvedOnly
      );
      setExceptions(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load exceptions');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  useEffect(() => {
    if (selectedRun) {
      fetchExceptions();
    }
  }, [selectedRun, filterType, unresolvedOnly]);

  const stats = {
    total: exceptions.length,
    high: exceptions.filter(e => e.severity === 'high').length,
    medium: exceptions.filter(e => e.severity === 'medium').length,
    low: exceptions.filter(e => e.severity === 'low').length,
    unresolved: exceptions.filter(e => !e.is_resolved).length
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Exceptions</h1>
          <p className="text-slate-500">Review and resolve reconciliation exceptions</p>
        </div>
        <button
          onClick={fetchExceptions}
          className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 flex items-center gap-2"
        >
          <RefreshCw size={18} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="bg-white rounded-xl shadow-sm p-4">
          <p className="text-sm text-slate-500">Total</p>
          <p className="text-2xl font-bold text-slate-900">{stats.total}</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm p-4 border-l-4 border-red-500">
          <p className="text-sm text-slate-500">High Severity</p>
          <p className="text-2xl font-bold text-red-600">{stats.high}</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm p-4 border-l-4 border-yellow-500">
          <p className="text-sm text-slate-500">Medium Severity</p>
          <p className="text-2xl font-bold text-yellow-600">{stats.medium}</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm p-4 border-l-4 border-blue-500">
          <p className="text-sm text-slate-500">Low Severity</p>
          <p className="text-2xl font-bold text-blue-600">{stats.low}</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm p-4">
          <p className="text-sm text-slate-500">Unresolved</p>
          <p className="text-2xl font-bold text-slate-900">{stats.unresolved}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl shadow-sm p-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <Filter size={18} className="text-slate-400" />
            <span className="text-sm font-medium text-slate-700">Filters:</span>
          </div>

          <select
            value={selectedRun}
            onChange={(e) => setSelectedRun(e.target.value)}
            className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Select Run</option>
            {history.map((run) => (
              <option key={run.run_id} value={run.run_id}>
                {run.start_date} ({run.exception_count} exceptions)
              </option>
            ))}
          </select>

          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
          >
            {EXCEPTION_TYPES.map((type) => (
              <option key={type.value} value={type.value}>{type.label}</option>
            ))}
          </select>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={unresolvedOnly}
              onChange={(e) => setUnresolvedOnly(e.target.checked)}
              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            Unresolved only
          </label>

          {(filterType || unresolvedOnly) && (
            <button
              onClick={() => {
                setFilterType('');
                setUnresolvedOnly(false);
              }}
              className="text-sm text-slate-500 hover:text-slate-700 flex items-center gap-1"
            >
              <X size={14} />
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* Exception List */}
      {loading ? (
        <div className="flex justify-center py-12">
          <RefreshCw className="animate-spin text-slate-400" size={32} />
        </div>
      ) : exceptions.length > 0 ? (
        <div className="space-y-4">
          {exceptions.map((exception) => (
            <ExceptionCard
              key={exception.exception_id}
              exception={exception}
              onResolve={fetchExceptions}
            />
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm p-12 text-center">
          <CheckCircle size={48} className="mx-auto text-green-300 mb-4" />
          <p className="text-slate-500">No exceptions found</p>
          <p className="text-sm text-slate-400 mt-1">
            {unresolvedOnly ? 'All exceptions have been resolved' : 'Run a reconciliation to see exceptions'}
          </p>
        </div>
      )}
    </div>
  );
}
