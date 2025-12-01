import axios from 'axios';

const API_BASE = '/api';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Status
export const getStatus = () => api.get('/status');

// Reconciliation
export const runDemoReconciliation = () => api.post('/reconcile/demo');

export const uploadAndReconcile = (file, startDate, endDate, bankAccountId = 'CHECKING-001') => {
  const formData = new FormData();
  formData.append('file', file);
  return api.post(
    `/reconcile/upload?start_date=${startDate}&end_date=${endDate}&bank_account_id=${bankAccountId}`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  );
};

export const getReconciliationHistory = (limit = 10) =>
  api.get(`/reconcile/history?limit=${limit}`);

export const getReconciliationDetail = (runId) =>
  api.get(`/reconcile/${runId}`);

// Market Data
export const getMarketSnapshot = () => api.get('/market/snapshot');

export const getStockQuote = (ticker) => api.get(`/market/quote/${ticker}`);

export const getEconomicIndicators = () => api.get('/market/economic');

export const validateVendor = (vendorName) =>
  api.get(`/market/validate-vendor/${encodeURIComponent(vendorName)}`);

// Exceptions
export const getExceptions = (runId = null, exceptionType = null, unresolvedOnly = false) => {
  const params = new URLSearchParams();
  if (runId) params.append('run_id', runId);
  if (exceptionType) params.append('exception_type', exceptionType);
  if (unresolvedOnly) params.append('unresolved_only', 'true');
  return api.get(`/exceptions?${params.toString()}`);
};

export const resolveException = (exceptionId, notes) =>
  api.post(`/exceptions/${exceptionId}/resolve`, { resolution_notes: notes });

// Reports
export const getReportUrl = (runId, format) => `${API_BASE}/reports/${runId}/${format}`;

export default api;
