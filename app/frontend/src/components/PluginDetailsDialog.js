'use client';

import { useEffect, useState, useRef } from 'react';
import { get } from '@/api/api-client';

/**
 * PluginDetailsDialog - A modal dialog for displaying complete plugin information and logs
 *
 * @param {Object} props
 * @param {boolean} props.isOpen - Whether the dialog is open
 * @param {function} props.onClose - Callback when dialog is closed
 * @param {Object} props.plugin - Plugin configuration data (from enabled_plugins)
 * @param {Object} props.execution - Plugin execution data (from plugin_executions)
 */
export default function PluginDetailsDialog({
  isOpen,
  onClose,
  plugin,
  execution
}) {
  const [logs, setLogs] = useState([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const logsContainerRef = useRef(null);

  // Close on ESC key
  useEffect(() => {
    function handleEscape(e) {
      if (e.key === 'Escape') onClose();
    }
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    }
  }, [isOpen, onClose]);

  // Lock body scroll when dialog is open
  useEffect(() => {
    if (isOpen) {
      // Save current scroll position
      const scrollY = window.scrollY;
      document.body.style.overflow = 'hidden';
      document.body.style.position = 'fixed';
      document.body.style.top = `-${scrollY}px`;
      document.body.style.width = '100%';

      return () => {
        // Restore scroll position
        document.body.style.overflow = '';
        document.body.style.position = '';
        document.body.style.top = '';
        document.body.style.width = '';
        window.scrollTo(0, scrollY);
      };
    }
  }, [isOpen]);

  // Load logs when dialog opens or execution changes
  useEffect(() => {
    if (isOpen && execution?.execution_id) {
      loadLogs();
    } else {
      setLogs([]);
    }
  }, [isOpen, execution?.execution_id]);

  // Auto-refresh logs for running plugins
  useEffect(() => {
    let interval;
    if (autoRefresh && isOpen && execution?.execution_id && execution?.status === 'running') {
      interval = setInterval(() => {
        loadLogs();
      }, 3000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, isOpen, execution?.execution_id, execution?.status]);

  async function loadLogs() {
    if (!execution?.execution_id) return;

    try {
      setLogsLoading(true);
      const response = await get(`/api/plugins/executions/${execution.execution_id}/logs`, {
        query: { limit: 500 }
      });
      setLogs(response.logs || []);
    } catch (e) {
      console.error('Error loading plugin logs:', e);
    } finally {
      setLogsLoading(false);
    }
  }

  function scrollToBottom() {
    if (logsContainerRef.current) {
      logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight;
    }
  }

  function getStatusColor(status) {
    switch (status) {
      case 'running': return '#065f46';
      case 'completed': return '#064e3b';
      case 'failed': return '#7f1d1d';
      default: return '#374151';
    }
  }

  function getStatusTextColor(status) {
    switch (status) {
      case 'running': return '#d1fae5';
      case 'completed': return '#d1fae5';
      case 'failed': return '#fecaca';
      default: return '#d1d5db';
    }
  }

  function getLogLevelColor(level) {
    switch (level) {
      case 'ERROR': return '#dc2626';
      case 'WARNING': return '#f59e0b';
      case 'INFO': return '#3b82f6';
      case 'DEBUG': return '#6b7280';
      default: return '#9ca3af';
    }
  }

  function formatTimestamp(timestamp) {
    if (!timestamp) return '';
    return new Date(timestamp).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  }

  if (!isOpen) return null;

  const pluginName = plugin?.name || execution?.plugin_name || 'Unknown Plugin';
  const status = execution?.status || 'unknown';

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: '#1e293b',
          borderRadius: '12px',
          padding: '24px',
          maxWidth: '1200px',
          width: '90%',
          maxHeight: '90vh',
          overflow: 'hidden',
          boxShadow: '0 4px 6px rgba(0, 0, 0, 0.3)',
          display: 'flex',
          flexDirection: 'column'
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ marginBottom: '16px', borderBottom: '1px solid #374151', paddingBottom: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ fontSize: '24px' }}>
                {pluginName === 'auto_analyzer' && '🤖'}
                {pluginName === 'performance_monitor' && '📈'}
                {pluginName !== 'auto_analyzer' && pluginName !== 'performance_monitor' && '🔌'}
              </span>
              <h2 style={{ margin: 0, fontSize: '20px', color: '#f1f5f9' }}>
                {pluginName}
              </h2>
              <span
                style={{
                  fontSize: '12px',
                  padding: '4px 10px',
                  borderRadius: '12px',
                  backgroundColor: getStatusColor(status),
                  color: getStatusTextColor(status),
                  fontWeight: '500'
                }}
              >
                {status === 'completed' ? '✓ completed' : status}
              </span>
            </div>
            <button
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                color: '#94a3b8',
                fontSize: '24px',
                cursor: 'pointer',
                padding: '0',
                width: '32px',
                height: '32px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
              title="Close (ESC)"
            >
              ×
            </button>
          </div>
        </div>

        {/* Content - Scrollable */}
        <div style={{ flex: 1, overflow: 'auto', paddingRight: '8px' }}>
          {/* Execution Details */}
          {execution && (
            <div style={{ marginBottom: '20px' }}>
              <h3 style={{ fontSize: '14px', color: '#9ca3af', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Execution Details
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '8px 16px', fontSize: '14px' }}>
                <span style={{ color: '#9ca3af' }}>Execution ID:</span>
                <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>{execution.execution_id}</span>

                {execution.started_at && (
                  <>
                    <span style={{ color: '#9ca3af' }}>Started:</span>
                    <span>{new Date(execution.started_at).toLocaleString()}</span>
                  </>
                )}

                {execution.completed_at && (
                  <>
                    <span style={{ color: '#9ca3af' }}>Completed:</span>
                    <span>{new Date(execution.completed_at).toLocaleString()}</span>
                  </>
                )}
              </div>

              {execution.error_message && (
                <div
                  style={{
                    marginTop: '12px',
                    padding: '12px',
                    backgroundColor: '#7f1d1d',
                    border: '1px solid #dc2626',
                    borderRadius: '6px',
                    fontSize: '13px',
                    color: '#fca5a5'
                  }}
                >
                  <strong>Error:</strong> {execution.error_message}
                </div>
              )}
            </div>
          )}

          {/* Parameters/Settings */}
          {plugin?.settings && Object.keys(plugin.settings).length > 0 && (
            <div style={{ marginBottom: '20px' }}>
              <h3 style={{ fontSize: '14px', color: '#9ca3af', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Parameters
              </h3>
              <div
                style={{
                  padding: '12px',
                  backgroundColor: '#0f172a',
                  borderRadius: '6px',
                  fontSize: '13px',
                  fontFamily: 'monospace',
                  border: '1px solid #334155'
                }}
              >
                {Object.entries(plugin.settings).map(([key, value]) => (
                  <div key={key} style={{ color: '#d1d5db', marginBottom: '6px' }}>
                    <span style={{ color: '#9ca3af' }}>{key}:</span>{' '}
                    <span style={{ color: '#60a5fa' }}>{JSON.stringify(value)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Logs Section */}
          {execution?.execution_id && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h3 style={{ fontSize: '14px', color: '#9ca3af', margin: 0, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Plugin Logs
                </h3>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {execution.status === 'running' && (
                    <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#9ca3af' }}>
                      <input
                        type="checkbox"
                        checked={autoRefresh}
                        onChange={(e) => setAutoRefresh(e.target.checked)}
                      />
                      Auto-refresh
                    </label>
                  )}
                  <button
                    className="btn"
                    onClick={loadLogs}
                    disabled={logsLoading}
                    style={{
                      fontSize: '11px',
                      padding: '4px 10px',
                      border: '1px solid #475569'
                    }}
                  >
                    {logsLoading ? 'Loading...' : '↻ Refresh'}
                  </button>
                  <button
                    className="btn"
                    onClick={scrollToBottom}
                    style={{
                      fontSize: '11px',
                      padding: '4px 10px',
                      border: '1px solid #475569'
                    }}
                  >
                    ↓ Bottom
                  </button>
                </div>
              </div>

              <div
                ref={logsContainerRef}
                style={{
                  maxHeight: '300px',
                  overflowY: 'auto',
                  backgroundColor: '#0f172a',
                  border: '1px solid #334155',
                  borderRadius: '6px',
                  padding: '12px',
                  fontSize: '12px',
                  fontFamily: 'monospace'
                }}
              >
                {logs.length === 0 ? (
                  <div style={{ color: '#6b7280', textAlign: 'center', padding: '20px' }}>
                    {logsLoading ? 'Loading logs...' : 'No logs available'}
                  </div>
                ) : (
                  logs.map((log, index) => (
                    <div
                      key={index}
                      style={{
                        marginBottom: '8px',
                        paddingBottom: '8px',
                        borderBottom: index < logs.length - 1 ? '1px solid #1e293b' : 'none'
                      }}
                    >
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'baseline' }}>
                        <span style={{ color: '#6b7280', fontSize: '11px' }}>
                          {formatTimestamp(log.timestamp)}
                        </span>
                        <span
                          style={{
                            color: getLogLevelColor(log.level),
                            fontWeight: '600',
                            fontSize: '11px'
                          }}
                        >
                          [{log.level}]
                        </span>
                        <span style={{ color: '#d1d5db', flex: 1, wordBreak: 'break-word' }}>
                          {log.message}
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {!execution && (
            <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>
              <div style={{ fontSize: '48px', marginBottom: '16px' }}>📋</div>
              <p>No execution data available for this plugin.</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid #374151' }}>
          <button
            onClick={onClose}
            style={{
              width: '100%',
              padding: '10px',
              borderRadius: '6px',
              border: '1px solid #475569',
              backgroundColor: '#334155',
              color: '#f1f5f9',
              cursor: 'pointer',
              fontSize: '14px',
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
