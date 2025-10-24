'use client';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { get, del, put, getWorkspaceFile, checkRevisionDependencies, deleteRevision as deleteRevisionApi, startRun, stopRun, restartRun, deleteRun, checkRunDependencies } from "@/api/api-client";
import Link from 'next/link';
import YamlEditor from '@/components/YamlEditor';
import ContextTag from '@/components/ContextTag';
import StarButton from '@/components/StarButton';
import DeleteConfirmationDialog from '@/components/DeleteConfirmationDialog';
import { useDeleteWithConfirmation } from '@/hooks/useDeleteWithConfirmation';

export default function RevisionDetail() {
  const params = useParams();
  const router = useRouter();
  const [revision, setRevision] = useState(null);
  const [experiment, setExperiment] = useState(null);
  const [environment, setEnvironment] = useState(null);
  const [runs, setRuns] = useState([]);
  const [yamlContent, setYamlContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [yamlExpanded, setYamlExpanded] = useState(false);
  const [isEditingNotes, setIsEditingNotes] = useState(false);
  const [notesText, setNotesText] = useState('');
  const [notesLoading, setNotesLoading] = useState(false);
  const [restartDialog, setRestartDialog] = useState({ isOpen: false, runId: null, runInfo: null });
  const [stopDialog, setStopDialog] = useState({ isOpen: false, runId: null, runInfo: null });
  const [deleteRunDialog, setDeleteRunDialog] = useState({ isOpen: false, runId: null, runInfo: null, warnings: null });

  // Delete confirmation hook
  const deleteHook = useDeleteWithConfirmation(
    checkRevisionDependencies,
    deleteRevisionApi,
    () => router.push('/revisions'),
    (error) => setError(`Error deleting revision: ${error.message}`)
  );

  useEffect(() => {
    if (params.id) {
      loadData();
    }
  }, [params.id]);

  async function loadData() {
    try {
      setLoading(true);
      
      const revisionData = await get(`/api/revisions/${params.id}`);
      setRevision(revisionData);
      setNotesText(revisionData.results_text || '');

      const [experimentData, environmentData, runsData] = await Promise.all([
        get(`/api/experiments/${revisionData.experiment_id}`),
        revisionData.environment_id ? get(`/api/environments/${revisionData.environment_id}`) : null,
        get('/api/runs', { query: { revision_id: params.id } })
      ]);
      
      setExperiment(experimentData);
      setEnvironment(environmentData);
      setRuns(runsData.runs || runsData);

      if (revisionData.yaml_path) {
        try {
          const yaml = await getWorkspaceFile(revisionData.yaml_path);
          setYamlContent(yaml);
        } catch (e) {
          console.error('Error loading YAML content:', e);
        }
      }
    } catch (e) {
      setError(`Error loading revision: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }

  function handleDeleteRevision() {
    deleteHook.initiateDelete(params.id, revision?.name, 'revision');
  }

  async function saveNotes() {
    try {
      setNotesLoading(true);
      setError('');
      
      const updatedRevision = await put(`/api/revisions/${params.id}/results`, null, {
        query: { results_text: notesText }
      });
      
      setRevision(updatedRevision);
      setIsEditingNotes(false);
    } catch (e) {
      setError(`Error saving notes: ${e.message}`);
    } finally {
      setNotesLoading(false);
    }
  }

  function cancelEditNotes() {
    setNotesText(revision?.results_text || '');
    setIsEditingNotes(false);
  }

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
      loadData();
    } catch (e) {
      setError(`Error ${action}ing run: ${e.message}`);
    }
  }

  function handleRestartClick(run) {
    setRestartDialog({
      isOpen: true,
      runId: run._id,
      runInfo: {
        id: run._id.slice(-8),
        experiment: experiment?.name,
        revision: `${revision.name} v${revision.version}`
      }
    });
  }

  async function handleRestartConfirm() {
    await controlRun(restartDialog.runId, 'restart');
    setRestartDialog({ isOpen: false, runId: null, runInfo: null });
  }

  function handleStopClick(run) {
    setStopDialog({
      isOpen: true,
      runId: run._id,
      runInfo: {
        id: run._id.slice(-8),
        experiment: experiment?.name,
        revision: `${revision.name} v${revision.version}`
      }
    });
  }

  async function handleStopConfirm() {
    await controlRun(stopDialog.runId, 'stop');
    setStopDialog({ isOpen: false, runId: null, runInfo: null });
  }

  async function handleDeleteRunClick(run) {
    try {
      const warnings = await checkRunDependencies(run._id);
      setDeleteRunDialog({
        isOpen: true,
        runId: run._id,
        runInfo: {
          id: run._id.slice(-8),
          experiment: experiment?.name,
          revision: `${revision.name} v${revision.version}`
        },
        warnings
      });
    } catch (e) {
      setError(`Error checking dependencies: ${e.message}`);
    }
  }

  async function handleDeleteRunConfirm() {
    try {
      setError('');
      await deleteRun(deleteRunDialog.runId, true);
      setDeleteRunDialog({ isOpen: false, runId: null, runInfo: null, warnings: null });
      loadData();
    } catch (e) {
      setError(`Error deleting run: ${e.message}`);
      setDeleteRunDialog({ isOpen: false, runId: null, runInfo: null, warnings: null });
    }
  }

  function formatDate(dateString) {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  function getStatusColor(status) {
    switch (status) {
      case 'running': return '#059669';
      case 'succeeded': return '#10b981';
      case 'failed': return '#dc2626';
      case 'stopped': return '#f59e0b';
      case 'pending': return '#6b7280';
      case 'created': return '#6b7280';
      default: return '#6b7280';
    }
  }

  if (loading) {
    return <div className="card"><p>Loading...</p></div>;
  }

  if (error && !revision) {
    return (
      <div className="card">
        <div style={{ background: '#dc2626', color: 'white', padding: '12px', borderRadius: '8px' }}>
          {error}
        </div>
        <Link href="/revisions" className="btn" style={{ marginTop: '16px', display: 'inline-block' }}>
          Back to Revisions
        </Link>
      </div>
    );
  }

  if (!revision) {
    return (
      <div className="card">
        <p>Revision not found</p>
        <Link href="/revisions" className="btn">Back to Revisions</Link>
      </div>
    );
  }

  return (
    <>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '16px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0, flex: 1 }}>
                <ContextTag type="revision" label="Revision" id={`v${revision.version}`} />
                <h1 style={{ margin: '0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{revision.name}</h1>
              </div>
              <StarButton
                entityType="revision"
                entityId={revision._id}
                isFavorite={revision.is_favorite || false}
                size="medium"
                onToggle={(newFavoriteState, updatedEntity) => {
                  // Update the revision in the local state
                  setRevision({ ...revision, is_favorite: newFavoriteState });
                }}
              />
            </div>
            <p style={{ color: '#9ca3af', margin: '0' }}>
              Created: {formatDate(revision.created_at)}
            </p>
          </div>
          
          <div style={{ display: 'flex', gap: '8px' }}>
            <Link
              href={`/runs/new?revision_id=${revision._id}`}
              className="btn"
              style={{ fontSize: '18px', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #10b981' }}
              title="New Run"
            >
              ▷
            </Link>
            <Link
              href={`/revisions/new?parent_revision_id=${revision._id}`}
              className="btn"
              style={{ fontSize: '18px', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #06b6d4' }}
              title="Promote"
            >
              ↗
            </Link>
            <button
              className="btn"
              style={{ fontSize: '18px', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #ef4444' }}
              onClick={handleDeleteRevision}
              title="Delete"
            >
              ×
            </button>
          </div>
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

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '24px' }}>
          <div>
            <h3>General Information</h3>
            <table style={{ width: '100%' }}>
              <tbody>
                <tr>
                  <td style={{ padding: '8px 0', fontWeight: 'bold' }}>Experiment:</td>
                  <td style={{ padding: '8px 0' }}>
                    {experiment && (
                      <Link href={`/experiments/${experiment._id}`}>
                        {experiment.name}
                      </Link>
                    )}
                  </td>
                </tr>
                <tr>
                  <td style={{ padding: '8px 0', fontWeight: 'bold' }}>Environment:</td>
                  <td style={{ padding: '8px 0' }}>
                    {environment ? `${environment.name} (v${environment.version})` : 'Not specified'}
                  </td>
                </tr>
                <tr>
                  <td style={{ padding: '8px 0', fontWeight: 'bold' }}>Parent Revision:</td>
                  <td style={{ padding: '8px 0' }}>
                    {revision.parent_revision_id ? (
                      <Link href={`/revisions/${revision.parent_revision_id}`}>
                        View parent
                      </Link>
                    ) : 'None'}
                  </td>
                </tr>
                <tr>
                  <td style={{ padding: '8px 0', fontWeight: 'bold' }}>Parent Run:</td>
                  <td style={{ padding: '8px 0' }}>
                    {revision.parent_run_id ? (
                      <Link href={`/runs/${revision.parent_run_id}`} style={{ fontFamily: 'monospace' }}>
                        {revision.parent_run_id.slice(-8)}
                      </Link>
                    ) : 'None'}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <h3 style={{ margin: 0 }}>Default CLI Flags</h3>
              <span style={{
                background: '#374151',
                color: '#9ca3af',
                fontSize: '10px',
                padding: '2px 6px',
                borderRadius: '4px',
                textTransform: 'uppercase',
                letterSpacing: '0.5px'
              }}>
                🔒 Immutable
              </span>
            </div>
            {revision.cli_flags && Object.keys(revision.cli_flags).length > 0 ? (
              <div style={{
                background: '#0b0f14',
                border: '1px solid #374151',
                borderRadius: '6px',
                padding: '12px'
              }}>
                <pre style={{ margin: 0, fontSize: '12px', fontFamily: 'monospace' }}>
                  {JSON.stringify(revision.cli_flags, null, 2)}
                </pre>
              </div>
            ) : (
              <p style={{ color: '#9ca3af' }}>No CLI flags configured</p>
            )}
          </div>
        </div>

        {revision.description && (
          <div style={{ marginBottom: '24px' }}>
            <h3>Description</h3>
            <p style={{ whiteSpace: 'pre-wrap' }}>{revision.description}</p>
          </div>
        )}

        <div style={{ marginBottom: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h3>Results Notes</h3>
            {!isEditingNotes ? (
              <button
                className="btn"
                style={{ fontSize: '12px', border: '1px solid #06b6d4' }}
                onClick={() => setIsEditingNotes(true)}
              >
                {revision.results_text ? 'Edit' : 'Add'}
              </button>
            ) : (
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  className="btn"
                  style={{ fontSize: '12px', border: '1px solid #10b981' }}
                  onClick={saveNotes}
                  disabled={notesLoading}
                >
                  {notesLoading ? 'Saving...' : 'Save'}
                </button>
                <button
                  className="btn"
                  style={{ fontSize: '12px', border: '1px solid #6b7280' }}
                  onClick={cancelEditNotes}
                  disabled={notesLoading}
                >
                  Cancel
                </button>
              </div>
            )}
          </div>

          {isEditingNotes ? (
            <textarea
              value={notesText}
              onChange={(e) => setNotesText(e.target.value)}
              placeholder="Write your results notes here..."
              style={{
                width: '100%',
                minHeight: '120px',
                background: '#0b0f14',
                border: '1px solid #374151',
                borderRadius: '6px',
                padding: '12px',
                color: 'white',
                fontFamily: 'inherit',
                fontSize: '14px',
                lineHeight: '1.5',
                resize: 'vertical'
              }}
              disabled={notesLoading}
            />
          ) : (
            <div style={{
              background: '#0b0f14',
              border: '1px solid #374151',
              borderRadius: '6px',
              padding: '12px',
              minHeight: '120px',
              whiteSpace: 'pre-wrap',
              color: revision.results_text ? 'white' : '#9ca3af'
            }}>
              {revision.results_text ||
                'No results notes. Click "Add" to write notes.'
              }
            </div>
          )}
        </div>

        {yamlContent && (
          <div style={{ marginBottom: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <h3 style={{ margin: 0 }}>YAML Configuration</h3>
                <span style={{
                  background: '#374151',
                  color: '#9ca3af',
                  fontSize: '10px',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px'
                }}>
                  🔒 Immutable
                </span>
              </div>
              <button
                className="btn"
                onClick={() => setYamlExpanded(!yamlExpanded)}
                style={{
                  border: '1px solid #374151',
                  fontSize: '12px',
                  padding: '6px 12px'
                }}
              >
                {yamlExpanded ? '⌃ Collapse' : '⌄ Expand'}
              </button>
            </div>
            <div style={{
              maxHeight: yamlExpanded ? 'none' : '400px',
              overflowY: yamlExpanded ? 'visible' : 'auto'
            }}>
              <YamlEditor
                value={yamlContent}
                onChange={() => {}} // No-op for read-only
                height={yamlExpanded ? `${Math.max(600, yamlContent.split('\n').length * 18)}px` : "400px"}
                readOnly={true}
              />
            </div>
          </div>
        )}

        <div>
          <h3>Runs based on this Revision ({runs.length})</h3>
          {runs.length === 0 ? (
            <p style={{ color: '#9ca3af' }}>No runs based on this revision</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Status</th>
                  <th>Started</th>
                  <th>Ended</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.map(run => (
                  <tr key={run._id}>
                    <td>
                      <Link href={`/runs/${run._id}`} style={{ fontFamily: 'monospace' }}>
                        {run._id.slice(-8)}
                      </Link>
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
                    <td>{run.started_at ? formatDate(run.started_at) : '-'}</td>
                    <td>{run.ended_at ? formatDate(run.ended_at) : '-'}</td>
                    <td>
                      <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
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
                          onClick={() => handleDeleteRunClick(run)}
                          title="Delete"
                        >
                          🗑
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Delete Revision Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={deleteHook.isDialogOpen}
        onClose={deleteHook.cancelDelete}
        onConfirm={deleteHook.confirmDelete}
        title="Delete Revision"
        itemName={deleteHook.pendingDelete?.itemName}
        itemType="revision"
        warnings={deleteHook.warnings}
      />

      {/* Restart Run Confirmation Dialog */}
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

      {/* Stop Run Confirmation Dialog */}
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

      {/* Delete Run Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={deleteRunDialog.isOpen}
        onClose={() => setDeleteRunDialog({ isOpen: false, runId: null, runInfo: null, warnings: null })}
        onConfirm={handleDeleteRunConfirm}
        title="Confirm Deletion"
        itemName={deleteRunDialog.runInfo ? `Run ${deleteRunDialog.runInfo.id}` : ''}
        itemType="run"
        warnings={deleteRunDialog.warnings}
      />
    </>
  );
}