'use client';
import { useEffect, useState } from 'react';
import { getRevisions, getExperiments, getEnvironments, checkRevisionDependencies, deleteRevision } from "@/api/api-client";
import Link from 'next/link';
import StarButton from '@/components/StarButton';
import DeleteConfirmationDialog from '@/components/DeleteConfirmationDialog';
import { useDeleteWithConfirmation } from '@/hooks/useDeleteWithConfirmation';

export default function Revisions() {
  const [revisions, setRevisions] = useState([]);
  const [experiments, setExperiments] = useState([]);
  const [environments, setEnvironments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Delete confirmation hook
  const deleteHook = useDeleteWithConfirmation(
    checkRevisionDependencies,
    deleteRevision,
    () => loadData(),
    (error) => setError(`Error deleting revision: ${error.message}`)
  );

  async function loadData() {
    try {
      setLoading(true);
      setError('');

      const [revisionsData, experimentsData, environmentsData] = await Promise.all([
        getRevisions(),
        getExperiments(),
        getEnvironments()
      ]);

      setRevisions(revisionsData);
      setExperiments(experimentsData);
      setEnvironments(environmentsData);
    } catch (e) {
      setError(`Error loading data: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  function handleDeleteRevision(id, name) {
    deleteHook.initiateDelete(id, name, 'revision');
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

  function getExperimentName(experimentId) {
    const exp = experiments.find(e => e._id === experimentId);
    return exp ? exp.name : 'Unknown';
  }

  function getEnvironmentName(environmentId) {
    const env = environments.find(e => e._id === environmentId);
    return env ? env.name : 'Unknown';
  }

  return (
    <>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h2>Revisions</h2>
          <Link href="/revisions/new" className="btn">
            New Revision
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

        {loading ? (
          <p>Loading revisions...</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: '40px' }}></th>
                <th>Version</th>
                <th>Name</th>
                <th>Experiment</th>
                <th>Description</th>
                <th>Environment</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {revisions.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', color: '#9ca3af' }}>
                    No revisions created
                  </td>
                </tr>
              ) : (
                revisions.map(rev => (
                  <tr key={rev._id}>
                    <td style={{ textAlign: 'center' }}>
                      <StarButton 
                        entityType="revision"
                        entityId={rev._id}
                        isFavorite={rev.is_favorite || false}
                        size="small"
                        onToggle={(newFavoriteState, updatedEntity) => {
                          // Update the revision in the local state
                          setRevisions(revisions.map(r => 
                            r._id === rev._id ? { ...r, is_favorite: newFavoriteState } : r
                          ));
                        }}
                      />
                    </td>
                    <td>
                      <span style={{ 
                        background: '#374151', 
                        padding: '2px 6px', 
                        borderRadius: '4px', 
                        fontSize: '12px',
                        fontFamily: 'monospace'
                      }}>
                        v{rev.version}
                      </span>
                    </td>
                    <td>
                      <Link href={`/revisions/${rev._id}`} style={{ fontWeight: 'bold' }}>
                        {rev.name}
                      </Link>
                    </td>
                    <td>
                      <Link href={`/experiments/${rev.experiment_id}`}>
                        {getExperimentName(rev.experiment_id)}
                      </Link>
                    </td>
                    <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {rev.description || '-'}
                    </td>
                    <td>{getEnvironmentName(rev.environment_id)}</td>
                    <td>{formatDate(rev.created_at)}</td>
                    <td>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <Link href={`/revisions/${rev._id}`} className="btn" style={{ fontSize: '16px', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #60a5fa' }} title="View">
                          ○
                        </Link>
                        <Link
                          href={`/runs/new?revision_id=${rev._id}`}
                          className="btn"
                          style={{ fontSize: '16px', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #10b981' }}
                          title="New Run"
                        >
                          ▷
                        </Link>
                        <button
                          className="btn"
                          style={{
                            fontSize: '16px',
                            width: '32px',
                            height: '32px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            padding: '0',
                            border: '1px solid #ef4444'
                          }}
                          onClick={() => handleDeleteRevision(rev._id, rev.name)}
                          title="Delete"
                        >
                          ×
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={deleteHook.isDialogOpen}
        onClose={deleteHook.cancelDelete}
        onConfirm={deleteHook.confirmDelete}
        title="Delete Revision"
        itemName={deleteHook.pendingDelete?.itemName}
        itemType="revision"
        warnings={deleteHook.warnings}
      />
    </>
  );
}