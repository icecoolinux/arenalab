'use client';
import { useEffect, useState, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { get, post, del, put, getWorkspaceFile, checkRunDependencies, deleteRun as deleteRunApi } from "@/api/api-client";
import Link from 'next/link';
import YamlEditor from '@/components/YamlEditor';
import ContextTag from '@/components/ContextTag';
import StarButton from '@/components/StarButton';
import DeleteConfirmationDialog from '@/components/DeleteConfirmationDialog';
import { useDeleteWithConfirmation } from '@/hooks/useDeleteWithConfirmation';

export default function RunDetail() {
  const params = useParams();
  const router = useRouter();
  const [run, setRun] = useState(null);
  const [experiment, setExperiment] = useState(null);
  const [revision, setRevision] = useState(null);
  const [logs, setLogs] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [logsLoading, setLogsLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [isEditingNotes, setIsEditingNotes] = useState(false);
  const [notesText, setNotesText] = useState('');
  const [notesLoading, setNotesLoading] = useState(false);
  const [yamlContent, setYamlContent] = useState('');
  const [yamlExpanded, setYamlExpanded] = useState(false);
  const [tensorboardUrl, setTensorboardUrl] = useState(null);
  const [tensorboardAvailable, setTensorboardAvailable] = useState(false);
  const [runPluginExecutions, setRunPluginExecutions] = useState([]);
  const [pluginNotes, setPluginNotes] = useState([]);
  const [health, setHealth] = useState(null);
  const [showHealthDetails, setShowHealthDetails] = useState(false);
  const logsContainerRef = useRef(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [autoScrollLogs, setAutoScrollLogs] = useState(false);
  const [showRestartDialog, setShowRestartDialog] = useState(false);

  // Delete confirmation hook
  const deleteHook = useDeleteWithConfirmation(
    checkRunDependencies,
    deleteRunApi,
    () => router.push('/runs'),
    (error) => setError(`Error deleting run: ${error.message}`)
  );

  useEffect(() => {
    if (params.id) {
      loadRunData();
    }
  }, [params.id]);

  useEffect(() => {
    let interval;
    if (autoRefresh && (run?.status === 'running' || run?.status === 'starting')) {
      interval = setInterval(() => {
        loadRunStatus();
        loadLogs();
        checkHealth(); // Auto-check health for running processes
      }, 5000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, run?.status]);

  useEffect(() => {
    let interval;
    // Check TensorBoard availability every 2 seconds if not available
    if (run && !tensorboardAvailable) {
      interval = setInterval(() => {
        checkTensorboardAvailability();
      }, 2000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [run, tensorboardAvailable]);

  // Scroll detection function (defined outside useEffect so it can be reused)
  const handleScroll = () => {
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    const scrollHeight = document.documentElement.scrollHeight;
    const clientHeight = document.documentElement.clientHeight;

    // Show button if not at bottom (with 100px threshold)
    const isAtBottom = scrollTop + clientHeight >= scrollHeight - 100;
    setShowScrollToBottom(!isAtBottom);
  };

  useEffect(() => {
    window.addEventListener('scroll', handleScroll);
    // Check initial position after a short delay to ensure content is rendered
    const timer = setTimeout(handleScroll, 100);

    return () => {
      window.removeEventListener('scroll', handleScroll);
      clearTimeout(timer);
    };
  }, []);

  // Re-check scroll position after data loads
  useEffect(() => {
    if (!loading && run) {
      // Small delay to ensure DOM has updated
      const timer = setTimeout(handleScroll, 100);
      return () => clearTimeout(timer);
    }
  }, [loading, run]);

  // Auto-scroll logs when enabled
  useEffect(() => {
    if (autoScrollLogs && logsContainerRef.current) {
      logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight;
    }
  }, [logs, autoScrollLogs]);

  // Detect manual scroll in logs container
  useEffect(() => {
    const logsContainer = logsContainerRef.current;
    if (!logsContainer) return;

    const handleLogsScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = logsContainer;
      const isAtBottom = scrollTop + clientHeight >= scrollHeight - 10;

      // If user scrolls away from bottom, disable auto-scroll
      if (autoScrollLogs && !isAtBottom) {
        setAutoScrollLogs(false);
      }
    };

    logsContainer.addEventListener('scroll', handleLogsScroll);
    return () => logsContainer.removeEventListener('scroll', handleLogsScroll);
  }, [autoScrollLogs]);

  async function loadRunData() {
    try {
      setLoading(true);
      const runData = await get(`/api/runs/${params.id}`);
      setRun(runData);

      const [expData, revData] = await Promise.all([
        get(`/api/experiments/${runData.experiment_id}`),
        get(`/api/revisions/${runData.revision_id}`)
      ]);
      
      setExperiment(expData);
      setRevision(revData);
      setNotesText(runData.results_text || '');

      if (runData.yaml_path) {
        try {
          const yaml = await getWorkspaceFile(runData.yaml_path);
          setYamlContent(yaml);
        } catch (e) {
          console.error('Error loading YAML content:', e);
        }
      }
      
      if (runData.status === 'running' || runData.status === 'starting' || runData.status === 'succeeded' || runData.status === 'failed' || runData.status === 'stopped' || runData.status === 'killed') {
        loadLogs();
      }

      // Check TensorBoard availability
      checkTensorboardAvailability();

      // Load plugin data for this run
      loadRunPluginData();

      // Check health immediately if running/starting
      if (runData.status === 'running' || runData.status === 'starting') {
        try {
          const healthData = await get(`/api/runs/${params.id}/health`);
          setHealth(healthData);
        } catch (e) {
          console.error('Error checking initial health:', e);
        }
      }
    } catch (e) {
      setError(`Error loading run: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function loadRunPluginData() {
    try {
      // Load plugin executions for this run
      const pluginResponse = await get('/api/plugins/executions', { 
        query: { target_id: params.id, scope: 'run' } 
      });
      setRunPluginExecutions(pluginResponse.executions || []);
      
      // Extract plugin notes if available
      if (run?.plugin_notes) {
        setPluginNotes(run.plugin_notes);
      }
    } catch (e) {
      console.error('Error loading plugin data:', e.message);
    }
  }

  async function loadRunStatus() {
    try {
      const statusData = await get(`/api/runs/${params.id}/status`);
      console.log(statusData);
      if (run) {
        const prevStatus = run.status;
        setRun(prev => ({ ...prev, ...statusData }));

        // If run just completed, check TensorBoard availability
        if (prevStatus !== 'succeeded' && statusData.status === 'succeeded') {
          setTimeout(() => {
            checkTensorboardAvailability();
          }, 2000); // Give TensorBoard more time to generate data
        }
      }
    } catch (e) {
      console.error('Error loading run status:', e);
    }
  }

  async function loadLogs() {
    try {
      setLogsLoading(true);
      const logResponse = await fetch(`/api/runs/${params.id}/logs`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (logResponse.ok) {
        const logText = await logResponse.text();
        setLogs(logText);
      }
    } catch (e) {
      console.error('Error loading logs:', e);
    } finally {
      setLogsLoading(false);
    }
  }

  async function controlRun(action, mode = null) {
    try {
      setError('');
      let response;

      if (action === 'execute') {
        response = await post(`/api/runs/${params.id}/execute`);
      } else if (action === 'stop') {
        response = await post(`/api/runs/${params.id}/stop`);
      } else if (action === 'restart') {
        const url = mode ? `/api/runs/${params.id}/restart?mode=${mode}` : `/api/runs/${params.id}/restart`;
        response = await post(url);
      }

      await loadRunData();
    } catch (e) {
      const actionText = action === 'execute' ? 'executing' :
                        action === 'stop' ? 'stopping' :
                        action === 'restart' ? 'restarting' : action;
      setError(`Error ${actionText} run: ${e.message}`);
    }
  }

  function handleDeleteRun() {
    deleteHook.initiateDelete(params.id, run?.name || run?._id, 'run');
  }

  async function saveNotes() {
    try {
      setNotesLoading(true);
      setError('');
      
      const updatedRun = await put(`/api/runs/${params.id}/results`, null, {
        query: { results_text: notesText }
      });
      
      setRun(updatedRun);
      setIsEditingNotes(false);
    } catch (e) {
      setError(`Error saving notes: ${e.message}`);
    } finally {
      setNotesLoading(false);
    }
  }

  function cancelEditNotes() {
    setNotesText(run?.results_text || '');
    setIsEditingNotes(false);
  }

  async function checkHealth() {
    if (!run || (run.status !== 'running' && run.status !== 'starting')) {
      setHealth(null);
      return;
    }

    try {
      const healthData = await get(`/api/runs/${params.id}/health`);
      setHealth(healthData);
    } catch (e) {
      console.error('Error checking health:', e);
    }
  }

  async function forceKillRun() {
    if (!confirm('Are you sure you want to force terminate this run? This action cannot be undone.')) {
      return;
    }

    try {
      setError('');
      await post(`/api/runs/${params.id}/force-kill`);
      await loadRunData();
      setHealth(null);
    } catch (e) {
      setError(`Error forcing termination: ${e.message}`);
    }
  }

  async function checkTensorboardAvailability() {
    if (!run) return;

    try {
      const response = await fetch(`/api/runs/${run._id}/tensorboard`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setTensorboardUrl(data.url);
        setTensorboardAvailable(data.available);
      } else {
        setTensorboardUrl(null);
        setTensorboardAvailable(false);
      }
    } catch (error) {
      console.error('Error checking TensorBoard availability:', error);
      setTensorboardUrl(null);
      setTensorboardAvailable(false);
    }
  }

  function formatDate(dateString) {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('es-ES', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  }

  function getStatusColor(status) {
    switch (status) {
      case 'running': return '#059669';
      case 'succeeded': return '#10b981';
      case 'failed': return '#dc2626';
      case 'stopped': return '#f59e0b';
      case 'killed': return '#dc2626';
      case 'pending': return '#6b7280';
      case 'created': return '#3b82f6';  // Blue to indicate ready for execution
      default: return '#6b7280';
    }
  }

  function toggleAutoScrollLogs() {
    if (!autoScrollLogs) {
      // Enable auto-scroll and scroll to bottom immediately
      setAutoScrollLogs(true);
      if (logsContainerRef.current) {
        logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight;
      }
    } else {
      // Disable auto-scroll
      setAutoScrollLogs(false);
    }
  }

  function scrollPageToBottom() {
    window.scrollTo({
      top: document.documentElement.scrollHeight,
      behavior: 'smooth'
    });
  }

  if (loading) {
    return <div className="card"><p>Loading...</p></div>;
  }

  if (error && !run) {
    return (
      <div className="card">
        <div style={{ background: '#dc2626', color: 'white', padding: '12px', borderRadius: '8px' }}>
          {error}
        </div>
        <Link href="/runs" className="btn" style={{ marginTop: '16px', display: 'inline-block' }}>
          Back to Runs
        </Link>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="card">
        <p>Run not found</p>
        <Link href="/runs" className="btn">Back to Runs</Link>
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
                <ContextTag type="run" label="Run" id={run._id.slice(-8)} />
                <h1 style={{ margin: '0', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>
                  {run._id.slice(-8)}
                </h1>
              </div>
              <StarButton
                entityType="run"
                entityId={run._id}
                isFavorite={run.is_favorite || false}
                size="medium"
                onToggle={(newFavoriteState) => {
                  // Update the run in the local state
                  setRun({ ...run, is_favorite: newFavoriteState });
                }}
              />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              <span
                style={{
                  padding: '6px 12px',
                  borderRadius: '6px',
                  fontSize: '14px',
                  background: getStatusColor(run.status),
                  color: 'white',
                  fontWeight: 'bold'
                }}
              >
                {run.status || 'unknown'}
              </span>
              {(run.status === 'running' || run.status === 'starting') && (
                <label style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '14px' }}>
                  <input
                    type="checkbox"
                    checked={autoRefresh}
                    onChange={e => setAutoRefresh(e.target.checked)}
                  />
                  Auto-refresh
                </label>
              )}
              {health && health.stuck && (
                <span
                  style={{
                    padding: '6px 12px',
                    borderRadius: '6px',
                    fontSize: '14px',
                    background: '#f59e0b',
                    color: 'white',
                    fontWeight: 'bold',
                    cursor: 'pointer'
                  }}
                  onClick={() => setShowHealthDetails(!showHealthDetails)}
                  title="Click to view details"
                >
                  ⚠️ Possibly stuck
                </span>
              )}
            </div>
            {showHealthDetails && health && (
              <div style={{
                marginTop: '12px',
                padding: '12px',
                background: '#fef3c7',
                borderRadius: '6px',
                fontSize: '14px',
                color: '#78350f'
              }}>
                <div><strong>Health status:</strong> {health.healthy ? '✓ Healthy' : '⚠️ Unhealthy'}</div>
                <div><strong>Reason:</strong> {health.reason}</div>
                {health.runtime_seconds !== undefined && (
                  <div><strong>Runtime:</strong> {Math.floor(health.runtime_seconds / 60)}m {Math.floor(health.runtime_seconds % 60)}s</div>
                )}
                {health.seconds_since_log_update !== undefined && (
                  <div><strong>Last log activity:</strong> {health.seconds_since_log_update}s ago</div>
                )}
                {health.pid && <div><strong>PID:</strong> {health.pid}</div>}
              </div>
            )}
          </div>
          
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {run.status === 'created' && (
              <button
                className="btn"
                style={{ fontSize: '18px', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #10b981' }}
                onClick={() => controlRun('execute')}
                title="Execute this run with its immutable configuration"
              >
                ▷
              </button>
            )}
            
            {(run.status === 'running' || run.status === 'starting') && (
              <>
                <button
                  className="btn"
                  style={{ fontSize: '18px', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #ef4444' }}
                  onClick={() => controlRun('stop')}
                  title="Stop"
                >
                  ◼
                </button>
                {health && health.stuck && (
                  <button
                    className="btn"
                    style={{ fontSize: '18px', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '2px solid #dc2626', background: '#dc2626', color: 'white' }}
                    onClick={forceKillRun}
                    title="Force termination (stuck process)"
                  >
                    ⚠
                  </button>
                )}
              </>
            )}
            
            {(run.status === 'succeeded' || run.status === 'failed' || run.status === 'stopped' || run.status === 'killed') && (
              <button
                className="btn"
                style={{ fontSize: '18px', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #f59e0b' }}
                onClick={() => setShowRestartDialog(true)}
                title="Restart with the same immutable configuration"
              >
                ⟲
              </button>
            )}

            {(run.status === 'succeeded' || run.status === 'failed' || run.status === 'stopped' || run.status === 'killed') && (
              <Link
                href={`/revisions/new?parent_run_id=${run._id}`}
                className="btn"
                style={{ fontSize: '18px', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #06b6d4' }}
                title="Create new revision based on this run"
              >
                ↗
              </Link>
            )}

            <Link
              href={`/runs/new?source=${run._id}`}
              className="btn"
              style={{ fontSize: '18px', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #6366f1' }}
              title="Create new run based on this one"
            >
              ⊕
            </Link>

            <button
              className="btn"
              style={{ fontSize: '18px', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #ef4444' }}
              onClick={handleDeleteRun}
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

        {run.status === 'created' && (
          <div style={{
            background: '#1e3a5f',
            border: '2px solid #3b82f6',
            borderRadius: '8px',
            padding: '16px',
            marginBottom: '16px'
          }}>
            <div style={{ display: 'flex', alignItems: 'start', gap: '12px' }}>
              <div style={{ fontSize: '24px', lineHeight: '1' }}>ℹ️</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 'bold', marginBottom: '4px', fontSize: '16px', color: '#93c5fd' }}>
                  Run Created - Ready to Execute
                </div>
                <div style={{ fontSize: '14px', color: '#bfdbfe', lineHeight: '1.5' }}>
                  This run has been created with an immutable configuration but has not been executed yet.
                  Click the <strong>Execute button (▷)</strong> above to start the training process.
                </div>
              </div>
            </div>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '24px' }}>
          <div>
            <h3>General Information</h3>
            <table style={{ width: '100%' }}>
              <tbody>
                <tr>
                  <td style={{ padding: '8px 0', fontWeight: 'bold' }}>Run ID:</td>
                  <td style={{ padding: '8px 0', fontFamily: 'monospace' }}>{run._id}</td>
                </tr>
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
                  <td style={{ padding: '8px 0', fontWeight: 'bold' }}>Revision:</td>
                  <td style={{ padding: '8px 0' }}>
                    {revision && (
                      <Link href={`/revisions/${revision._id}`}>
                        v{revision.version} - {revision.name}
                      </Link>
                    )}
                  </td>
                </tr>
                <tr>
                  <td style={{ padding: '8px 0', fontWeight: 'bold' }}>Created:</td>
                  <td style={{ padding: '8px 0' }}>{formatDate(run.created_at)}</td>
                </tr>
                <tr>
                  <td style={{ padding: '8px 0', fontWeight: 'bold' }}>Started:</td>
                  <td style={{ padding: '8px 0' }}>{formatDate(run.started_at)}</td>
                </tr>
                <tr>
                  <td style={{ padding: '8px 0', fontWeight: 'bold' }}>Ended:</td>
                  <td style={{ padding: '8px 0' }}>{formatDate(run.ended_at)}</td>
                </tr>
                {(run.execution_count > 0) && (
                  <tr>
                    <td style={{ padding: '8px 0', fontWeight: 'bold' }}>Executions:</td>
                    <td style={{ padding: '8px 0' }}>
                      {run.execution_count}
                      {run.execution_count > 1 && (
                        <span style={{ color: '#9ca3af', fontSize: '12px', marginLeft: '8px' }}>
                          (restarted {run.execution_count - 1} time{run.execution_count > 2 ? 's' : ''})
                        </span>
                      )}
                    </td>
                  </tr>
                )}
                {run.last_restarted_at && (
                  <tr>
                    <td style={{ padding: '8px 0', fontWeight: 'bold' }}>Last restart:</td>
                    <td style={{ padding: '8px 0' }}>{formatDate(run.last_restarted_at)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <h3 style={{ margin: 0 }}>CLI Flags</h3>
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
            {run.cli_flags && Object.keys(run.cli_flags).length > 0 ? (
              <div style={{
                background: '#0b0f14',
                border: '1px solid #374151',
                borderRadius: '6px',
                padding: '12px'
              }}>
                <pre style={{ margin: 0, fontSize: '12px', fontFamily: 'monospace' }}>
                  {JSON.stringify(run.cli_flags, null, 2)}
                </pre>
              </div>
            ) : (
              <p style={{ color: '#9ca3af' }}>No CLI flags configured</p>
            )}
          </div>
        </div>

        {run.description && (
          <div style={{ marginBottom: '24px' }}>
            <h3>Description</h3>
            <p style={{ whiteSpace: 'pre-wrap' }}>{run.description}</p>
          </div>
        )}

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

        <div style={{ marginBottom: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h3>Results Notes</h3>
            {!isEditingNotes ? (
              <button
                className="btn"
                style={{ fontSize: '12px', border: '1px solid #06b6d4' }}
                onClick={() => setIsEditingNotes(true)}
              >
                {run.results_text ? 'Edit' : 'Add'}
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
                fontFamily: 'monospace',
                fontSize: '14px',
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
              minHeight: '40px'
            }}>
              {run.results_text ? (
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: '14px' }}>
                  {run.results_text}
                </pre>
              ) : (
                <p style={{ margin: 0, color: '#9ca3af', fontStyle: 'italic' }}>
                  No results notes. Click &quot;Add&quot; to write notes.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Plugin Information Section */}
        {(runPluginExecutions.length > 0 || pluginNotes.length > 0 || (experiment?.enabled_plugins && experiment.enabled_plugins.some(p => p.scope === 'run'))) && (
          <div style={{ marginBottom: '24px' }}>
            <h3 style={{ marginBottom: '16px' }}>🤖 AI Plugin Insights</h3>
            
            {/* Plugin-generated notes */}
            {pluginNotes.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ fontSize: '16px', marginBottom: '12px' }}>AI Analysis & Insights</h4>
                <div style={{ display: 'grid', gap: '8px' }}>
                  {pluginNotes.map((note, index) => (
                    <div 
                      key={index}
                      style={{
                        background: '#f0f9ff',
                        border: '1px solid #bfdbfe',
                        borderRadius: '8px',
                        padding: '12px'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                        <span style={{ fontWeight: '500', fontSize: '12px', color: '#1e40af' }}>
                          🤖 {note.plugin_name}
                        </span>
                        <span style={{ fontSize: '11px', color: '#6b7280' }}>
                          {new Date(note.timestamp).toLocaleString()}
                        </span>
                      </div>
                      <div style={{ color: '#374151', fontSize: '14px', lineHeight: '1.4' }}>
                        {note.content}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Active run plugins */}
            {runPluginExecutions.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ fontSize: '16px', marginBottom: '12px' }}>Active Run Plugins</h4>
                <div style={{ display: 'grid', gap: '8px' }}>
                  {runPluginExecutions.map((execution) => (
                    <div 
                      key={execution.execution_id}
                      style={{
                        border: '1px solid #e5e7eb',
                        borderRadius: '6px',
                        padding: '12px',
                        backgroundColor: execution.status === 'running' ? '#f0f9ff' : '#f9fafb'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontSize: '16px' }}>
                            {execution.plugin_name === 'auto_analyzer' && '📊'}
                            {execution.plugin_name === 'performance_monitor' && '📈'}
                          </span>
                          <span style={{ fontWeight: '500' }}>{execution.plugin_name}</span>
                          <span style={{ 
                            fontSize: '11px',
                            padding: '2px 6px',
                            borderRadius: '10px',
                            backgroundColor: execution.status === 'running' ? '#dcfce7' : 
                                           execution.status === 'completed' ? '#d1fae5' : '#fef2f2',
                            color: execution.status === 'running' ? '#166534' : 
                                  execution.status === 'completed' ? '#065f46' : '#991b1b'
                          }}>
                            {execution.status}
                          </span>
                        </div>
                        <div style={{ fontSize: '11px', color: '#6b7280' }}>
                          {execution.started_at && `Started: ${new Date(execution.started_at).toLocaleString()}`}
                        </div>
                      </div>
                      
                      {execution.error_message && (
                        <div style={{ 
                          marginTop: '8px',
                          fontSize: '11px',
                          color: '#dc2626',
                          backgroundColor: '#fef2f2',
                          padding: '6px 8px',
                          borderRadius: '4px'
                        }}>
                          Error: {execution.error_message}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* No plugins message */}
            {runPluginExecutions.length === 0 && pluginNotes.length === 0 && (
              <div style={{ 
                textAlign: 'center', 
                padding: '20px',
                color: '#6b7280',
                backgroundColor: '#f9fafb',
                borderRadius: '8px',
                border: '1px solid #e5e7eb'
              }}>
                <div style={{ fontSize: '24px', marginBottom: '8px' }}>🔌</div>
                <div style={{ fontSize: '14px' }}>
                  No run plugins active. 
                  <Link href="/plugins" style={{ color: '#3b82f6', textDecoration: 'none', marginLeft: '4px' }}>
                    Browse plugins →
                  </Link>
                </div>
              </div>
            )}
          </div>
        )}

        {(run.status === 'running' || run.status === 'starting' || run.status === 'succeeded' || run.status === 'failed' || run.status === 'stopped' || run.status === 'killed' || logs) && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <h3>Execution Logs</h3>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  className="btn"
                  onClick={loadLogs}
                  disabled={logsLoading}
                  style={{ fontSize: '12px' }}
                >
                  {logsLoading ? 'Loading...' : 'Refresh Logs'}
                </button>
                <a
                  href={tensorboardAvailable && tensorboardUrl ? tensorboardUrl : '#'}
                  target={tensorboardAvailable && tensorboardUrl ? "_blank" : "_self"}
                  rel="noopener noreferrer"
                  className="btn"
                  style={{
                    fontSize: '12px',
                    border: `1px solid ${tensorboardAvailable ? '#f59e0b' : '#6b7280'}`,
                    opacity: tensorboardAvailable ? 1 : 0.5,
                    cursor: tensorboardAvailable ? 'pointer' : 'not-allowed',
                    pointerEvents: tensorboardAvailable ? 'auto' : 'none'
                  }}
                  title={tensorboardAvailable ? "Open TensorBoard" : "TensorBoard data not available"}
                  onClick={tensorboardAvailable ? undefined : (e) => e.preventDefault()}
                >
                  TensorBoard
                </a>
              </div>
            </div>
            
            <div
              ref={logsContainerRef}
              style={{
                background: '#0b0f14',
                border: '1px solid #374151',
                borderRadius: '6px',
                padding: '12px',
                maxHeight: '400px',
                overflowY: 'auto',
                fontFamily: 'monospace',
                fontSize: '12px',
                whiteSpace: 'pre-wrap'
              }}
            >
              {logs ? logs : (
                <p style={{ color: '#9ca3af', margin: 0 }}>
                  {(run.status === 'created' || run.status === 'starting')
                    ? 'Logs will be available when execution starts'
                    : 'Loading logs...'}
                </p>
              )}
            </div>

            <div style={{ marginTop: '12px', display: 'flex', justifyContent: 'center' }}>
              <button
                className="btn"
                onClick={toggleAutoScrollLogs}
                style={{
                  fontSize: '12px',
                  border: `2px solid ${autoScrollLogs ? '#10b981' : '#6366f1'}`,
                  background: autoScrollLogs ? '#10b981' : 'transparent',
                  color: autoScrollLogs ? 'white' : 'inherit',
                  fontWeight: autoScrollLogs ? 'bold' : 'normal'
                }}
                title={autoScrollLogs ? "Auto-scroll enabled (click to disable)" : "Enable auto-scroll to end"}
              >
                {autoScrollLogs ? '✓ Auto-scroll Active' : '↓ Scroll to End'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Restart Mode Dialog */}
      {showRestartDialog && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000
          }}
          onClick={() => setShowRestartDialog(false)}
        >
          <div
            style={{
              background: '#1a1f2e',
              padding: '32px',
              borderRadius: '12px',
              maxWidth: '500px',
              width: '90%',
              border: '1px solid #374151'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ marginTop: 0, marginBottom: '16px', fontSize: '24px' }}>
              How do you want to restart?
            </h2>
            <p style={{ marginBottom: '24px', color: '#9ca3af', lineHeight: '1.6' }}>
              Select restart mode:
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '24px' }}>
              <button
                className="btn"
                style={{
                  width: '100%',
                  padding: '16px',
                  textAlign: 'left',
                  border: '1px solid #10b981',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-start'
                }}
                onClick={() => {
                  setShowRestartDialog(false);
                  controlRun('restart', 'resume');
                }}
              >
                <div style={{ fontWeight: 'bold', marginBottom: '4px', fontSize: '16px' }}>
                  ▶ Continue (--resume)
                </div>
                <div style={{ fontSize: '14px', color: '#9ca3af' }}>
                  Resumes training from the last saved checkpoint
                </div>
              </button>

              <button
                className="btn"
                style={{
                  width: '100%',
                  padding: '16px',
                  textAlign: 'left',
                  border: '1px solid #f59e0b',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-start'
                }}
                onClick={() => {
                  setShowRestartDialog(false);
                  controlRun('restart', 'force');
                }}
              >
                <div style={{ fontWeight: 'bold', marginBottom: '4px', fontSize: '16px' }}>
                  ⟲ Restart from scratch (--force)
                </div>
                <div style={{ fontSize: '14px', color: '#9ca3af' }}>
                  Overwrites existing checkpoints and starts from scratch
                </div>
              </button>
            </div>

            <button
              className="btn"
              style={{
                width: '100%',
                padding: '12px',
                border: '1px solid #6b7280'
              }}
              onClick={() => setShowRestartDialog(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={deleteHook.isDialogOpen}
        onClose={deleteHook.cancelDelete}
        onConfirm={deleteHook.confirmDelete}
        title="Delete Run"
        itemName={deleteHook.pendingDelete?.itemName}
        itemType="run"
        warnings={deleteHook.warnings}
      />

      {/* Floating Scroll to Bottom Button */}
      {showScrollToBottom && (
        <button
          onClick={scrollPageToBottom}
          style={{
            position: 'fixed',
            bottom: '24px',
            right: '24px',
            width: '56px',
            height: '56px',
            borderRadius: '50%',
            background: '#6366f1',
            color: 'white',
            border: 'none',
            fontSize: '24px',
            cursor: 'pointer',
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'all 0.3s ease',
            zIndex: 1000
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = '#4f46e5';
            e.currentTarget.style.transform = 'scale(1.1)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = '#6366f1';
            e.currentTarget.style.transform = 'scale(1)';
          }}
          title="Scroll to bottom"
        >
          ↓
        </button>
      )}
    </>
  );
}