'use client';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  getExperiment,
  getRevisions,
  getRuns,
  getPluginExecutions,
  getEnvironments,
  deleteExperiment,
  updateExperimentNotes,
  startPlugin,
  stopPlugin,
  checkExperimentDependencies
} from "@/api/api-client";
import Link from 'next/link';
import ContextTag from '@/components/ContextTag';
import StarButton from '@/components/StarButton';
import DeleteConfirmationDialog from '@/components/DeleteConfirmationDialog';
import { useDeleteWithConfirmation } from '@/hooks/useDeleteWithConfirmation';

export default function ExperimentDetail() {
  const params = useParams();
  const router = useRouter();
  const [experiment, setExperiment] = useState(null);
  const [revisions, setRevisions] = useState([]);
  const [runs, setRuns] = useState([]);
  const [environments, setEnvironments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('revisions');
  const [isEditingNotes, setIsEditingNotes] = useState(false);
  const [notesText, setNotesText] = useState('');
  const [notesLoading, setNotesLoading] = useState(false);
  const [pluginExecutions, setPluginExecutions] = useState([]);
  const [pluginsLoading, setPluginsLoading] = useState(false);

  // Delete confirmation hook
  const deleteHook = useDeleteWithConfirmation(
    checkExperimentDependencies,
    deleteExperiment,
    () => router.push('/experiments'),
    (error) => setError(`Error deleting experiment: ${error.message}`)
  );

  useEffect(() => {
    if (params.id) {
      loadData();
    }
  }, [params.id]);

  useEffect(() => {
    if (params.id && !loading) {
      // Refresh data when tab changes
      if (activeTab === 'revisions') {
        loadRevisions();
      } else if (activeTab === 'runs') {
        loadRuns();
      } else if (activeTab === 'plugins') {
        loadPlugins();
      }
    }
  }, [activeTab]);

  async function loadData() {
    try {
      setLoading(true);
      const [expData, revisionsData, runsData, envsData] = await Promise.all([
        getExperiment(params.id),
        getRevisions(params.id),
        getRuns({ experiment_id: params.id }),
        getEnvironments()
      ]);

      setExperiment(expData);
      setNotesText(expData.results_text || '');
      setRevisions(revisionsData);
      setRuns(runsData.runs || runsData);
      setEnvironments(envsData);

      // Load plugin executions for this experiment
      loadPlugins();
    } catch (e) {
      setError(`Error loading data: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function loadRevisions() {
    try {
      const revisionsData = await getRevisions(params.id);
      setRevisions(revisionsData);
    } catch (e) {
      console.error('Error loading revisions:', e.message);
    }
  }

  async function loadRuns() {
    try {
      const runsData = await getRuns({ experiment_id: params.id });
      setRuns(runsData.runs || runsData);
    } catch (e) {
      console.error('Error loading runs:', e.message);
    }
  }

  async function loadPlugins() {
    try {
      setPluginsLoading(true);
      const response = await getPluginExecutions(params.id, 'experiment');
      setPluginExecutions(response.executions || []);
    } catch (e) {
      console.error('Error loading plugin executions:', e.message);
    } finally {
      setPluginsLoading(false);
    }
  }

  function handleDeleteExperiment() {
    deleteHook.initiateDelete(params.id, experiment?.name, 'experiment');
  }

  async function saveNotes() {
    try {
      setNotesLoading(true);
      setError('');

      const updatedExperiment = await updateExperimentNotes(params.id, notesText);

      setExperiment(updatedExperiment);
      setIsEditingNotes(false);
    } catch (e) {
      setError(`Error saving notes: ${e.message}`);
    } finally {
      setNotesLoading(false);
    }
  }

  function cancelEditNotes() {
    setNotesText(experiment?.results_text || '');
    setIsEditingNotes(false);
  }

  async function stopPluginExecution(executionId) {
    try {
      setError('');
      await stopPlugin(executionId);
      loadPlugins();
    } catch (e) {
      setError(`Error stopping plugin: ${e.message}`);
    }
  }

  async function startPluginForExperiment(pluginName, settings = {}) {
    try {
      setError('');
      await startPlugin(pluginName, params.id, 'experiment', settings);
      loadPlugins();
    } catch (e) {
      setError(`Error starting plugin: ${e.message}`);
    }
  }

  function getPluginStatusIcon(status) {
    switch(status) {
      case 'running': return '🟢';
      case 'completed': return '✅';
      case 'failed': return '❌';
      case 'stopped': return '⏹️';
      case 'pending': return '🟡';
      default: return '❓';
    }
  }

  function getPluginStatusColor(status) {
    switch(status) {
      case 'running': return '#10b981';
      case 'completed': return '#059669';
      case 'failed': return '#dc2626';
      case 'stopped': return '#6b7280';
      case 'pending': return '#f59e0b';
      default: return '#6b7280';
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

  if (loading) {
    return <div className="card"><p>Loading...</p></div>;
  }

  if (error) {
    return (
      <div className="card">
        <div style={{ background: '#dc2626', color: 'white', padding: '12px', borderRadius: '8px' }}>
          {error}
        </div>
        <Link href="/experiments" className="btn" style={{ marginTop: '16px', display: 'inline-block' }}>
          Back to Experiments
        </Link>
      </div>
    );
  }

  if (!experiment) {
    return (
      <div className="card">
        <p>Experiment not found</p>
        <Link href="/experiments" className="btn">Back to Experiments</Link>
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
                <ContextTag type="experiment" label="Experiment" />
                <h1 style={{ margin: '0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{experiment.name}</h1>
              </div>
              <StarButton
                entityType="experiment"
                entityId={experiment._id}
                isFavorite={experiment.is_favorite || false}
                size="medium"
                onToggle={(newFavoriteState, updatedEntity) => {
                  // Update the experiment in the local state
                  setExperiment({ ...experiment, is_favorite: newFavoriteState });
                }}
              />
            </div>
            <p style={{ color: '#9ca3af', margin: '0' }}>
              Created: {formatDate(experiment.created_at)}
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <Link href={`/revisions/new?experiment_id=${experiment._id}`} className="btn" style={{ fontSize: '18px', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #10b981' }} title="New Revision">
              +
            </Link>
            <button
              className="btn"
              style={{ fontSize: '18px', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #ef4444' }}
              onClick={handleDeleteExperiment}
              title="Delete Experiment"
            >
              ×
            </button>
          </div>
        </div>

        {experiment.description && (
          <div style={{ marginBottom: '16px' }}>
            <h3>Description</h3>
            <p style={{ whiteSpace: 'pre-wrap' }}>{experiment.description}</p>
          </div>
        )}

        {experiment.tags && experiment.tags.length > 0 && (
          <div style={{ marginBottom: '16px' }}>
            <h3>Tags</h3>
            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
              {experiment.tags.map(tag => (
                <span
                  key={tag}
                  style={{
                    background: '#374151',
                    padding: '4px 8px',
                    borderRadius: '4px',
                    fontSize: '14px'
                  }}
                >
                  {tag}
                </span>
              ))}
            </div>
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
                {experiment.results_text ? 'Edit' : 'Add'}
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
              color: experiment.results_text ? 'white' : '#9ca3af'
            }}>
              {experiment.results_text ||
                'No results notes. Click "Add" to write notes.'
              }
            </div>
          )}
        </div>

        <div style={{ borderTop: '1px solid #374151', paddingTop: '16px' }}>
          <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
            <button
              className="btn"
              style={{ border: activeTab === 'revisions' ? '1px solid #60a5fa' : '1px solid #374151' }}
              onClick={() => setActiveTab('revisions')}
            >
              Revisions ({revisions.length})
            </button>
            <button
              className="btn"
              style={{ border: activeTab === 'runs' ? '1px solid #60a5fa' : '1px solid #374151' }}
              onClick={() => setActiveTab('runs')}
            >
              Runs ({runs.length})
            </button>
            <button
              className="btn"
              style={{ border: activeTab === 'plugins' ? '1px solid #60a5fa' : '1px solid #374151' }}
              onClick={() => setActiveTab('plugins')}
            >
              🔌 Plugins ({pluginExecutions.length})
            </button>
          </div>

          {activeTab === 'revisions' && (
            <div>
              <h3>Revisions</h3>
              {revisions.length === 0 ? (
                <p style={{ color: '#9ca3af' }}>No revisions created</p>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Version</th>
                      <th>Name</th>
                      <th>Description</th>
                      <th>Created</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {revisions.map(rev => (
                      <tr key={rev._id}>
                        <td>v{rev.version}</td>
                        <td>
                          <Link
                            href={`/revisions/${rev._id}`}
                            style={{ color: '#60a5fa', textDecoration: 'none' }}
                          >
                            {rev.name}
                          </Link>
                        </td>
                        <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {rev.description}
                        </td>
                        <td>{formatDate(rev.created_at)}</td>
                        <td>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <Link href={`/revisions/${rev._id}`} className="btn" style={{ fontSize: '16px', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #60a5fa' }} title="View">
                              ○
                            </Link>
                            <Link href={`/runs/new?revision_id=${rev._id}`} className="btn" style={{ fontSize: '16px', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #10b981' }} title="Run">
                              ▷
                            </Link>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {activeTab === 'runs' && (
            <div>
              <h3>Runs</h3>
              {runs.length === 0 ? (
                <p style={{ color: '#9ca3af' }}>No runs created</p>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Revision</th>
                      <th>Status</th>
                      <th>Started</th>
                      <th>Ended</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map(run => {
                      const revision = revisions.find(r => r._id === run.revision_id);
                      return (
                        <tr key={run._id}>
                          <td>
                            <Link
                              href={`/runs/${run._id}`}
                              style={{ color: '#60a5fa', textDecoration: 'none' }}
                            >
                              {run._id.slice(-8)}
                            </Link>
                          </td>
                          <td>
                            {revision ? (
                              <Link
                                href={`/revisions/${revision._id}`}
                                style={{ color: '#60a5fa', textDecoration: 'none' }}
                              >
                                {revision.name} (v{revision.version})
                              </Link>
                            ) : (
                              <span style={{ color: '#9ca3af' }}>-</span>
                            )}
                          </td>
                          <td>
                            <span
                              style={{
                                padding: '2px 6px',
                                borderRadius: '4px',
                                fontSize: '12px',
                                background: run.status === 'running' ? '#059669' :
                                           run.status === 'succeeded' ? '#10b981' :
                                           run.status === 'failed' ? '#dc2626' : '#6b7280'
                              }}
                            >
                              {run.status}
                            </span>
                          </td>
                          <td>{run.started_at ? formatDate(run.started_at) : '-'}</td>
                          <td>{run.ended_at ? formatDate(run.ended_at) : '-'}</td>
                          <td>
                            <Link href={`/runs/${run._id}`} className="btn" style={{ fontSize: '16px', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #60a5fa' }} title="View">
                              ○
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {activeTab === 'plugins' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3>Active Plugins</h3>
                {pluginsLoading && <span style={{ color: '#6b7280' }}>Loading...</span>}
              </div>

              {experiment?.enabled_plugins && experiment.enabled_plugins.length > 0 && (
                <div style={{ marginBottom: '24px' }}>
                  <h4 style={{ marginBottom: '12px', fontSize: '16px' }}>Enabled Plugins</h4>
                  <div style={{ display: 'grid', gap: '12px' }}>
                    {experiment.enabled_plugins.map((enabledPlugin) => {
                      // Find the most recent execution for this plugin (prioritize running, then sort by started_at)
                      const pluginExecutionsList = pluginExecutions.filter(e => e.plugin_name === enabledPlugin.name);
                      const execution = pluginExecutionsList.sort((a, b) => {
                        // Prioritize running status
                        if (a.status === 'running' && b.status !== 'running') return -1;
                        if (b.status === 'running' && a.status !== 'running') return 1;
                        // Then sort by most recent started_at
                        return new Date(b.started_at || 0) - new Date(a.started_at || 0);
                      })[0];
                      const isRunning = execution && execution.status === 'running';

                      return (
                        <div
                          key={enabledPlugin.name}
                          style={{
                            border: isRunning ? '1px solid #059669' : '1px solid #374151',
                            borderRadius: '8px',
                            padding: '16px',
                            backgroundColor: isRunning ? '#064e3b' : '#1a1f26'
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                            <div style={{ flex: 1 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                                <h5 style={{ margin: 0, fontWeight: '500', fontSize: '18px' }}>
                                  {enabledPlugin.name === 'pbt' && '🧠'}
                                  {enabledPlugin.name === 'hyperparameter_sweeper' && '🔍'}
                                  {enabledPlugin.name}
                                </h5>
                                {execution && (
                                  <span style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '4px',
                                    fontSize: '14px',
                                    color: getPluginStatusColor(execution.status)
                                  }}>
                                    {getPluginStatusIcon(execution.status)} {execution.status}
                                  </span>
                                )}
                              </div>
                              
                              {execution && execution.started_at && (
                                <div style={{ fontSize: '14px', color: '#9ca3af', marginBottom: '8px' }}>
                                  Started: {formatDate(execution.started_at)}
                                  {execution.completed_at && ` • Completed: ${formatDate(execution.completed_at)}`}
                                </div>
                              )}

                              {execution && execution.error_message && execution.status === 'failed' && (
                                <div style={{
                                  fontSize: '14px',
                                  color: '#fca5a5',
                                  backgroundColor: '#450a0a',
                                  padding: '8px',
                                  borderRadius: '4px',
                                  marginTop: '8px'
                                }}>
                                  Error: {execution.error_message}
                                </div>
                              )}

                              {execution && execution.generation > 0 && (
                                <div style={{ fontSize: '14px', color: '#10b981', marginTop: '4px' }}>
                                  Generation: {execution.generation}
                                </div>
                              )}

                              {enabledPlugin.settings && Object.keys(enabledPlugin.settings).length > 0 && (
                                <details style={{ marginTop: '8px' }}>
                                  <summary style={{ fontSize: '14px', color: '#9ca3af', cursor: 'pointer' }}>
                                    Settings
                                  </summary>
                                  <div style={{
                                    fontSize: '14px',
                                    color: '#d1d5db',
                                    marginTop: '4px',
                                    padding: '8px',
                                    backgroundColor: '#0b0f14',
                                    borderRadius: '4px'
                                  }}>
                                    {Object.entries(enabledPlugin.settings).map(([key, value]) => (
                                      <div key={key}>
                                        <strong>{key}:</strong> {JSON.stringify(value)}
                                      </div>
                                    ))}
                                  </div>
                                </details>
                              )}
                            </div>

                            <div style={{ display: 'flex', gap: '8px' }}>
                              {!execution && (
                                <button
                                  onClick={() => startPluginForExperiment(enabledPlugin.name, enabledPlugin.settings)}
                                  style={{
                                    padding: '6px 12px',
                                    fontSize: '12px',
                                    backgroundColor: '#059669',
                                    color: 'white',
                                    border: 'none',
                                    borderRadius: '4px',
                                    cursor: 'pointer'
                                  }}
                                >
                                  ▶️ Start
                                </button>
                              )}
                              
                              {execution && execution.status === 'running' && (
                                <button
                                  onClick={() => stopPluginExecution(execution.execution_id)}
                                  style={{
                                    padding: '6px 12px',
                                    fontSize: '12px',
                                    backgroundColor: '#dc2626',
                                    color: 'white',
                                    border: 'none',
                                    borderRadius: '4px',
                                    cursor: 'pointer'
                                  }}
                                >
                                  ⏹️ Stop
                                </button>
                              )}

                              {execution && execution.status !== 'running' && execution.status !== 'pending' && (
                                <button
                                  onClick={() => startPluginForExperiment(enabledPlugin.name, enabledPlugin.settings)}
                                  style={{
                                    padding: '6px 12px',
                                    fontSize: '12px',
                                    backgroundColor: '#3b82f6',
                                    color: 'white',
                                    border: 'none',
                                    borderRadius: '4px',
                                    cursor: 'pointer'
                                  }}
                                >
                                  🔄 Restart
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {pluginExecutions.length > 0 && (
                <div>
                  <h4 style={{ marginBottom: '12px', fontSize: '16px' }}>Execution History</h4>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Plugin</th>
                        <th>Status</th>
                        <th>Started</th>
                        <th>Completed</th>
                        <th>Generation</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pluginExecutions.map((execution) => (
                        <tr key={execution.execution_id}>
                          <td style={{ fontWeight: '500' }}>
                            {execution.plugin_name === 'pbt' && '🧠 '}
                            {execution.plugin_name === 'auto_analyzer' && '📊 '}
                            {execution.plugin_name === 'hyperparameter_sweeper' && '🔍 '}
                            {execution.plugin_name}
                          </td>
                          <td>
                            <span style={{ 
                              display: 'flex', 
                              alignItems: 'center', 
                              gap: '4px',
                              color: getPluginStatusColor(execution.status)
                            }}>
                              {getPluginStatusIcon(execution.status)} {execution.status}
                            </span>
                          </td>
                          <td>{execution.started_at ? formatDate(execution.started_at) : '-'}</td>
                          <td>{execution.completed_at ? formatDate(execution.completed_at) : '-'}</td>
                          <td>{execution.generation || 0}</td>
                          <td>
                            {execution.status === 'running' ? (
                              <button
                                onClick={() => stopPluginExecution(execution.execution_id)}
                                style={{
                                  padding: '4px 8px',
                                  fontSize: '11px',
                                  backgroundColor: '#dc2626',
                                  color: 'white',
                                  border: 'none',
                                  borderRadius: '4px',
                                  cursor: 'pointer'
                                }}
                              >
                                Stop
                              </button>
                            ) : (
                              <span style={{ color: '#6b7280', fontSize: '12px' }}>-</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {(!experiment?.enabled_plugins || experiment.enabled_plugins.length === 0) && pluginExecutions.length === 0 && (
                <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>
                  <div style={{ fontSize: '48px', marginBottom: '16px' }}>🔌</div>
                  <h4 style={{ marginBottom: '8px' }}>No plugins enabled</h4>
                  <p style={{ margin: 0 }}>
                    Plugins can automate experiment management, hyperparameter optimization, and analysis.
                  </p>
                  <Link 
                    href="/plugins" 
                    style={{ 
                      color: '#3b82f6', 
                      textDecoration: 'none',
                      fontSize: '14px',
                      marginTop: '8px',
                      display: 'inline-block'
                    }}
                  >
                    Browse Available Plugins →
                  </Link>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={deleteHook.isDialogOpen}
        onClose={deleteHook.cancelDelete}
        onConfirm={deleteHook.confirmDelete}
        title="Delete Experiment"
        itemName={deleteHook.pendingDelete?.itemName}
        itemType="experiment"
        warnings={deleteHook.warnings}
      />
    </>
  );
}