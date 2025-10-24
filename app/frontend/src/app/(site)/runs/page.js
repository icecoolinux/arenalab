'use client';
import { useEffect, useState } from 'react';
import { getRuns, getExperiments, getRevisions, startRun, stopRun, restartRun, deleteRun, checkRunDependencies } from "@/api/api-client";
import Link from 'next/link';
import StarButton from '@/components/StarButton';
import DeleteConfirmationDialog from '@/components/DeleteConfirmationDialog';

export default function Runs() {
  const [runs, setRuns] = useState([]);
  const [experiments, setExperiments] = useState([]);
  const [revisions, setRevisions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState({
    status: '',
    limit: 50,
    offset: 0
  });
  const [total, setTotal] = useState(0);
  const [restartDialog, setRestartDialog] = useState({ isOpen: false, runId: null, runInfo: null });
  const [stopDialog, setStopDialog] = useState({ isOpen: false, runId: null, runInfo: null });
  const [deleteDialog, setDeleteDialog] = useState({ isOpen: false, runId: null, runInfo: null, warnings: null });

  async function loadRuns() {
    try {
      setLoading(true);
      setError('');

      const query = {};
      if (filters.status) query.status = filters.status;
      query.limit = filters.limit;
      query.offset = filters.offset;

      const [runsData, experimentsData, revisionsData] = await Promise.all([
        getRuns(query),
        getExperiments(),
        getRevisions()
      ]);

      setRuns(runsData.runs || runsData);
      setTotal(runsData.total || (runsData.runs ? runsData.runs.length : runsData.length));
      setExperiments(experimentsData);
      setRevisions(revisionsData);
    } catch (e) {
      setError(`Error loading runs: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRuns();
  }, [filters]);

  async function controlRun(runId, action) {
    try {
      setError('');
      if (action === 'start') {
        await startRun(runId);
      } else if (action === 'stop') {
        await stopRun(runId);
      } else if (action === 'restart') {
        await restartRun(runId);
      }
      loadRuns();
    } catch (e) {
      setError(`Error ${action}ing run: ${e.message}`);
    }
  }

  function handleRestartClick(run) {
    const experimentName = getExperimentName(run.experiment_id);
    const revisionInfo = getRevisionInfo(run.revision_id);
    setRestartDialog({
      isOpen: true,
      runId: run._id,
      runInfo: {
        id: run._id.slice(-8),
        experiment: experimentName,
        revision: `${revisionInfo.name} v${revisionInfo.version}`
      }
    });
  }

  async function handleRestartConfirm() {
    await controlRun(restartDialog.runId, 'restart');
    setRestartDialog({ isOpen: false, runId: null, runInfo: null });
  }

  function handleStopClick(run) {
    const experimentName = getExperimentName(run.experiment_id);
    const revisionInfo = getRevisionInfo(run.revision_id);
    setStopDialog({
      isOpen: true,
      runId: run._id,
      runInfo: {
        id: run._id.slice(-8),
        experiment: experimentName,
        revision: `${revisionInfo.name} v${revisionInfo.version}`
      }
    });
  }

  async function handleStopConfirm() {
    await controlRun(stopDialog.runId, 'stop');
    setStopDialog({ isOpen: false, runId: null, runInfo: null });
  }

  async function handleDeleteClick(run) {
    const experimentName = getExperimentName(run.experiment_id);
    const revisionInfo = getRevisionInfo(run.revision_id);

    try {
      const warnings = await checkRunDependencies(run._id);
      setDeleteDialog({
        isOpen: true,
        runId: run._id,
        runInfo: {
          id: run._id.slice(-8),
          experiment: experimentName,
          revision: `${revisionInfo.name} v${revisionInfo.version}`
        },
        warnings
      });
    } catch (e) {
      setError(`Error checking dependencies: ${e.message}`);
    }
  }

  async function handleDeleteConfirm() {
    try {
      setError('');
      await deleteRun(deleteDialog.runId, true);
      setDeleteDialog({ isOpen: false, runId: null, runInfo: null, warnings: null });
      loadRuns();
    } catch (e) {
      setError(`Error deleting run: ${e.message}`);
      setDeleteDialog({ isOpen: false, runId: null, runInfo: null, warnings: null });
    }
  }

  function formatDate(dateString) {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  function getExperimentName(experimentId) {
    const exp = experiments.find(e => e._id === experimentId);
    return exp ? exp.name : 'Unknown';
  }

  function getRevisionInfo(revisionId) {
    const rev = revisions.find(r => r._id === revisionId);
    return rev ? { name: rev.name, version: rev.version } : { name: 'Unknown', version: 0 };
  }

  function getStatusColor(status) {
    switch (status) {
      case 'running': return '#059669';
      case 'succeeded': return '#10b981';
      case 'failed': return '#dc2626';
      case 'stopped': return '#f59e0b';
      case 'killed': return '#dc2626';
      case 'pending': return '#6b7280';
      default: return '#6b7280';
    }
  }

  function handleFilterChange(key, value) {
    setFilters(prev => ({ ...prev, [key]: value, offset: 0 }));
  }

  function handlePagination(direction) {
    const newOffset = direction === 'next' 
      ? filters.offset + filters.limit 
      : Math.max(0, filters.offset - filters.limit);
    
    setFilters(prev => ({ ...prev, offset: newOffset }));
  }

  return (
    <>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '8px' }}>
          <h2>Runs</h2>
          <Link href="/runs/new" className="btn">
            New Run
          </Link>
        </div>

        {error && (
          <div style={{ 
            background: '#dc2626', 
            color: 'white', 
            padding: '12px', 
            borderRadius: '8px', 
            marginBottom: '16px' 
          }}>
            {error}
          </div>
        )}

        <div style={{ 
          display: 'flex', 
          gap: '12px', 
          marginBottom: '16px', 
          alignItems: 'center',
          flexWrap: 'wrap' 
        }}>
          <select 
            className="input" 
            value={filters.status}
            onChange={e => handleFilterChange('status', e.target.value)}
            style={{ width: 'auto', minWidth: '150px' }}
          >
            <option value="">All statuses</option>
            <option value="created">Created</option>
            <option value="pending">Pending</option>
            <option value="running">Running</option>
            <option value="succeeded">Succeeded</option>
            <option value="failed">Failed</option>
            <option value="stopped">Stopped</option>
            <option value="killed">Killed</option>
          </select>

          <select 
            className="input" 
            value={filters.limit}
            onChange={e => handleFilterChange('limit', parseInt(e.target.value))}
            style={{ width: 'auto', minWidth: '100px' }}
          >
            <option value={25}>25 per page</option>
            <option value={50}>50 per page</option>
            <option value={100}>100 per page</option>
          </select>

          <span style={{ color: '#9ca3af', fontSize: '14px' }}>
            Total: {total} runs
          </span>
        </div>

        {loading ? (
          <p>Loading runs...</p>
        ) : (
          <>
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: '40px' }}></th>
                  <th>ID</th>
                  <th>Experiment</th>
                  <th>Revision</th>
                  <th>Status</th>
                  <th>Started</th>
                  <th>Ended</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={{ textAlign: 'center', color: '#9ca3af' }}>
                      No runs found
                    </td>
                  </tr>
                ) : (
                  runs.map(run => (
                    <tr key={run._id}>
                      <td style={{ textAlign: 'center' }}>
                        <StarButton 
                          entityType="run"
                          entityId={run._id}
                          isFavorite={run.is_favorite || false}
                          size="small"
                          onToggle={(newFavoriteState, updatedEntity) => {
                            // Update the run in the local state
                            setRuns(runs.map(r => 
                              r._id === run._id ? { ...r, is_favorite: newFavoriteState } : r
                            ));
                          }}
                        />
                      </td>
                      <td>
                        <Link href={`/runs/${run._id}`} style={{ fontFamily: 'monospace' }}>
                          {run._id.slice(-8)}
                        </Link>
                      </td>
                      <td>
                        <Link href={`/experiments/${run.experiment_id}`}>
                          {getExperimentName(run.experiment_id)}
                        </Link>
                      </td>
                      <td>
                        {run.revision_id ? (
                          <Link href={`/revisions/${run.revision_id}`}>
                            {(() => {
                              const revInfo = getRevisionInfo(run.revision_id);
                              return `${revInfo.name} v${revInfo.version}`;
                            })()}
                          </Link>
                        ) : '-'}
                      </td>
                      <td>
                        <span 
                          style={{ 
                            padding: '4px 8px', 
                            borderRadius: '4px', 
                            fontSize: '12px',
                            background: getStatusColor(run.status),
                            color: 'white'
                          }}
                        >
                          {run.status || 'unknown'}
                        </span>
                      </td>
                      <td>{formatDate(run.started_at)}</td>
                      <td>{formatDate(run.ended_at)}</td>
                      <td>
                        <div style={{ display: 'flex', gap: '4px' }}>
                          <Link href={`/runs/${run._id}`} className="btn" style={{ fontSize: '16px', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #60a5fa' }} title="View">
                            ○
                          </Link>

                          {run.status === 'created' && (
                            <button
                              className="btn"
                              style={{ fontSize: '16px', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #10b981' }}
                              onClick={() => controlRun(run._id, 'start')}
                              title="Start"
                            >
                              ▷
                            </button>
                          )}

                          {run.status === 'running' && (
                            <button
                              className="btn"
                              style={{ fontSize: '16px', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #ef4444' }}
                              onClick={() => handleStopClick(run)}
                              title="Stop"
                            >
                              ◼
                            </button>
                          )}

                          {(run.status === 'failed' || run.status === 'stopped' || run.status === 'killed') && (
                            <button
                              className="btn"
                              style={{ fontSize: '16px', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #f59e0b' }}
                              onClick={() => handleRestartClick(run)}
                              title="Restart"
                            >
                              ⟲
                            </button>
                          )}

                          <button
                            className="btn"
                            style={{ fontSize: '16px', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #ef4444' }}
                            onClick={() => handleDeleteClick(run)}
                            title="Delete"
                          >
                            🗑
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>

            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginTop: '16px'
            }}>
              <div style={{ color: '#9ca3af', fontSize: '14px' }}>
                Showing {filters.offset + 1} - {Math.min(filters.offset + filters.limit, total)} of {total}
              </div>

              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  className="btn"
                  onClick={() => handlePagination('prev')}
                  disabled={filters.offset === 0}
                  style={{
                    opacity: filters.offset === 0 ? 0.5 : 1,
                    cursor: filters.offset === 0 ? 'not-allowed' : 'pointer'
                  }}
                >
                  Previous
                </button>
                <button
                  className="btn"
                  onClick={() => handlePagination('next')}
                  disabled={filters.offset + filters.limit >= total}
                  style={{
                    opacity: filters.offset + filters.limit >= total ? 0.5 : 1,
                    cursor: filters.offset + filters.limit >= total ? 'not-allowed' : 'pointer'
                  }}
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      <DeleteConfirmationDialog
        isOpen={restartDialog.isOpen}
        onClose={() => setRestartDialog({ isOpen: false, runId: null, runInfo: null })}
        onConfirm={handleRestartConfirm}
        title="Confirm Restart"
        message={
          restartDialog.runInfo ? (
            <>
              Are you sure you want to restart run{' '}
              <strong style={{ color: '#f1f5f9' }}>{restartDialog.runInfo.id}</strong>?
              <br /><br />
              <div style={{ fontSize: '14px', color: '#94a3b8' }}>
                <strong>Experiment:</strong> {restartDialog.runInfo.experiment}
                <br />
                <strong>Revision:</strong> {restartDialog.runInfo.revision}
              </div>
            </>
          ) : ''
        }
        confirmText="Restart"
        confirmColor="#f59e0b"
      />

      <DeleteConfirmationDialog
        isOpen={stopDialog.isOpen}
        onClose={() => setStopDialog({ isOpen: false, runId: null, runInfo: null })}
        onConfirm={handleStopConfirm}
        title="Confirm Stop"
        message={
          stopDialog.runInfo ? (
            <>
              Are you sure you want to stop run{' '}
              <strong style={{ color: '#f1f5f9' }}>{stopDialog.runInfo.id}</strong>?
              <br /><br />
              <div style={{ fontSize: '14px', color: '#94a3b8' }}>
                <strong>Experiment:</strong> {stopDialog.runInfo.experiment}
                <br />
                <strong>Revision:</strong> {stopDialog.runInfo.revision}
              </div>
            </>
          ) : ''
        }
        confirmText="Stop"
        confirmColor="#ef4444"
      />

      <DeleteConfirmationDialog
        isOpen={deleteDialog.isOpen}
        onClose={() => setDeleteDialog({ isOpen: false, runId: null, runInfo: null, warnings: null })}
        onConfirm={handleDeleteConfirm}
        title="Confirm Deletion"
        itemName={deleteDialog.runInfo ? `Run ${deleteDialog.runInfo.id}` : ''}
        itemType="run"
        warnings={deleteDialog.warnings}
      />
    </>
  );
}