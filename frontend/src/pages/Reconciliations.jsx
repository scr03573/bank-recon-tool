import React, { useState, useEffect } from 'react';
import {
  Upload,
  Play,
  RefreshCw,
  Download,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  XCircle,
  FileSpreadsheet
} from 'lucide-react';
import {
  getReconciliationHistory,
  getReconciliationDetail,
  runDemoReconciliation,
  uploadAndReconcile,
  getReportUrl
} from '../api';

function MatchRow({ match }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <tr
        className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="py-3 px-4">
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </td>
        <td className="py-3 px-4 text-sm">{match.bank_date}</td>
        <td className="py-3 px-4 text-sm font-medium">
          ${Math.abs(match.bank_amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}
        </td>
        <td className="py-3 px-4 text-sm text-slate-600 truncate max-w-xs">
          {match.bank_description}
        </td>
        <td className="py-3 px-4 text-sm text-slate-600">{match.vendor_name}</td>
        <td className="py-3 px-4">
          <span className={`text-sm font-medium ${
            match.confidence >= 0.95 ? 'text-green-600' :
            match.confidence >= 0.85 ? 'text-yellow-600' : 'text-red-600'
          }`}>
            {(match.confidence * 100).toFixed(0)}%
          </span>
        </td>
        <td className="py-3 px-4">
          <span className="px-2 py-1 text-xs bg-slate-100 text-slate-700 rounded">
            {match.match_type}
          </span>
        </td>
      </tr>
      {expanded && (
        <tr className="bg-slate-50">
          <td colSpan="7" className="px-4 py-3">
            <div className="text-sm">
              <p className="font-medium text-slate-700 mb-2">Match Details</p>
              <div className="grid grid-cols-2 gap-4 text-slate-600">
                <div>
                  <p><span className="font-medium">Bank TX ID:</span> {match.bank_transaction_id}</p>
                  <p><span className="font-medium">AP TX IDs:</span> {match.ap_transaction_ids.join(', ')}</p>
                </div>
                <div>
                  <p className="font-medium">Match Reasons:</p>
                  <ul className="list-disc list-inside text-xs">
                    {match.match_reasons.map((reason, i) => (
                      <li key={i}>{reason}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function Reconciliations() {
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [runDetail, setRunDetail] = useState(null);
  const [error, setError] = useState(null);

  // File upload state
  const [showUpload, setShowUpload] = useState(false);
  const [file, setFile] = useState(null);
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2024-01-31');

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const res = await getReconciliationHistory(20);
      setHistory(res.data);
      if (res.data.length > 0 && !selectedRun) {
        setSelectedRun(res.data[0].run_id);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load history');
    } finally {
      setLoading(false);
    }
  };

  const fetchDetail = async (runId) => {
    try {
      const res = await getReconciliationDetail(runId);
      setRunDetail(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load details');
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  useEffect(() => {
    if (selectedRun) {
      fetchDetail(selectedRun);
    }
  }, [selectedRun]);

  const handleRunDemo = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await runDemoReconciliation();
      await fetchHistory();
      setSelectedRun(res.data.run_id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to run demo');
    } finally {
      setRunning(false);
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) return;

    setRunning(true);
    setError(null);
    try {
      const res = await uploadAndReconcile(file, startDate, endDate);
      await fetchHistory();
      setSelectedRun(res.data.run_id);
      setShowUpload(false);
      setFile(null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to upload and reconcile');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Reconciliations</h1>
          <p className="text-slate-500">View and run bank reconciliations</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowUpload(!showUpload)}
            className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200 flex items-center gap-2"
          >
            <Upload size={18} />
            Upload File
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

      {/* Upload Form */}
      {showUpload && (
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h3 className="text-lg font-semibold mb-4">Upload Bank File</h3>
          <form onSubmit={handleUpload} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Bank File (CSV/Excel)</label>
              <input
                type="file"
                accept=".csv,.xlsx,.xls,.ofx,.qfx"
                onChange={(e) => setFile(e.target.files[0])}
                className="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Start Date</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">End Date</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={!file || running}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              Upload & Reconcile
            </button>
          </form>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Run History Sidebar */}
        <div className="bg-white rounded-xl shadow-sm p-4">
          <h3 className="font-semibold text-slate-900 mb-3">Run History</h3>
          {loading ? (
            <div className="flex justify-center py-8">
              <RefreshCw className="animate-spin text-slate-400" />
            </div>
          ) : history.length > 0 ? (
            <div className="space-y-2">
              {history.map((run) => (
                <button
                  key={run.run_id}
                  onClick={() => setSelectedRun(run.run_id)}
                  className={`w-full text-left p-3 rounded-lg transition-colors ${
                    selectedRun === run.run_id
                      ? 'bg-blue-50 border border-blue-200'
                      : 'hover:bg-slate-50 border border-transparent'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-900">
                      {run.start_date}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      run.status === 'completed' ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-600'
                    }`}>
                      {run.status}
                    </span>
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    {run.matched_count}/{run.total_bank_transactions} matched ({(run.match_rate * 100).toFixed(0)}%)
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-slate-400 text-sm py-4 text-center">No runs yet</p>
          )}
        </div>

        {/* Run Details */}
        <div className="lg:col-span-3 space-y-6">
          {runDetail ? (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-white rounded-xl shadow-sm p-4">
                  <p className="text-sm text-slate-500">Bank Transactions</p>
                  <p className="text-2xl font-bold text-slate-900">{runDetail.summary.total_bank_transactions}</p>
                </div>
                <div className="bg-white rounded-xl shadow-sm p-4">
                  <p className="text-sm text-slate-500">AP Transactions</p>
                  <p className="text-2xl font-bold text-slate-900">{runDetail.summary.total_ap_transactions}</p>
                </div>
                <div className="bg-white rounded-xl shadow-sm p-4">
                  <p className="text-sm text-slate-500">Match Rate</p>
                  <p className="text-2xl font-bold text-green-600">{(runDetail.summary.match_rate * 100).toFixed(1)}%</p>
                </div>
                <div className="bg-white rounded-xl shadow-sm p-4">
                  <p className="text-sm text-slate-500">Total Matched</p>
                  <p className="text-2xl font-bold text-slate-900">
                    ${(runDetail.summary.total_matched_amount / 1000).toFixed(0)}K
                  </p>
                </div>
              </div>

              {/* Reports */}
              <div className="bg-white rounded-xl shadow-sm p-4">
                <h3 className="font-semibold text-slate-900 mb-3">Download Reports</h3>
                <div className="flex gap-3">
                  {Object.entries(runDetail.report_paths || {}).map(([format, path]) => (
                    <a
                      key={format}
                      href={getReportUrl(runDetail.run_id, format)}
                      className="flex items-center gap-2 px-3 py-2 bg-slate-100 text-slate-700 rounded-lg hover:bg-slate-200"
                    >
                      <FileSpreadsheet size={16} />
                      {format.toUpperCase()}
                    </a>
                  ))}
                </div>
              </div>

              {/* Matches Table */}
              <div className="bg-white rounded-xl shadow-sm">
                <div className="p-4 border-b border-slate-200">
                  <h3 className="font-semibold text-slate-900">Matched Transactions ({runDetail.matches.length})</h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left text-slate-500 text-sm bg-slate-50">
                        <th className="py-3 px-4 font-medium w-8"></th>
                        <th className="py-3 px-4 font-medium">Date</th>
                        <th className="py-3 px-4 font-medium">Amount</th>
                        <th className="py-3 px-4 font-medium">Description</th>
                        <th className="py-3 px-4 font-medium">Vendor</th>
                        <th className="py-3 px-4 font-medium">Confidence</th>
                        <th className="py-3 px-4 font-medium">Type</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runDetail.matches.slice(0, 50).map((match) => (
                        <MatchRow key={match.match_id} match={match} />
                      ))}
                    </tbody>
                  </table>
                  {runDetail.matches.length > 50 && (
                    <div className="p-4 text-center text-slate-500 text-sm">
                      Showing 50 of {runDetail.matches.length} matches
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="bg-white rounded-xl shadow-sm p-12 text-center">
              <FileSpreadsheet size={48} className="mx-auto text-slate-300 mb-4" />
              <p className="text-slate-500">Select a run to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
