'use client';
import { useEffect, useState } from 'react';
import { getExperiments, createExperiment, deleteExperiment, getPlugins, checkExperimentDependencies } from "@/api/api-client";
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import StarButton from '@/components/StarButton';
import DeleteConfirmationDialog from '@/components/DeleteConfirmationDialog';
import { useDeleteWithConfirmation } from '@/hooks/useDeleteWithConfirmation';
import PluginCard from '@/components/PluginCard';

export default function Experiments() {
  const router = useRouter();
  const [experiments, setExperiments] = useState([]);
  const [form, setForm] = useState({
    name: '',
    description: '',
    tags: ''
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [plugins, setPlugins] = useState([]);
  const [selectedPlugins, setSelectedPlugins] = useState([]);
  const [pluginSettings, setPluginSettings] = useState({});

  // Delete confirmation hook
  const deleteHook = useDeleteWithConfirmation(
    checkExperimentDependencies,
    deleteExperiment,
    () => loadExperiments(), // Reload the list after successful delete
    (error) => setError(`Error deleting experiment: ${error.message}`)
  );

  async function loadExperiments() {
    try {
      setLoading(true);
      const res = await getExperiments();
      setExperiments(res);
    } catch (e) {
      setError(`Error loading experiments: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadExperiments();
    loadPlugins();
  }, []);

  async function loadPlugins() {
    try {
      const res = await getPlugins('experiment');
      setPlugins(res.plugins || []);
    } catch (e) {
      console.error('Error loading plugins:', e.message);
    }
  }

  async function handleCreateExperiment(e) {
    e.preventDefault();
    if (!form.name.trim()) {
      setError('Name is required');
      return;
    }

    try {
      setError('');
      const body = {
        ...form,
        tags: form.tags ? form.tags.split(',').map(s => s.trim()).filter(Boolean) : [],
        enabled_plugins: selectedPlugins.map(pluginName => ({
          name: pluginName,
          enabled: true,
          settings: pluginSettings[pluginName] || {},
          enabled_at: new Date().toISOString()
        }))
      };
      const newExperiment = await createExperiment(body);
      router.push(`/experiments/${newExperiment._id}`);
    } catch (e) {
      setError(`Error creating experiment: ${e.message}`);
    }
  }

  function handleDeleteExperiment(id, name) {
    deleteHook.initiateDelete(id, name, 'experiment');
  }

  function togglePlugin(pluginName) {
    if (selectedPlugins.includes(pluginName)) {
      setSelectedPlugins(selectedPlugins.filter(p => p !== pluginName));
      const newSettings = { ...pluginSettings };
      delete newSettings[pluginName];
      setPluginSettings(newSettings);
    } else {
      setSelectedPlugins([...selectedPlugins, pluginName]);
      // Initialize with default settings
      const plugin = plugins.find(p => p.name === pluginName);
      if (plugin && plugin.settings_schema) {
        const defaultSettings = {};
        Object.entries(plugin.settings_schema).forEach(([key, spec]) => {
          if (spec.default !== undefined) {
            defaultSettings[key] = spec.default;
          }
        });
        setPluginSettings({
          ...pluginSettings,
          [pluginName]: defaultSettings
        });
      }
    }
  }

  function updatePluginSetting(pluginName, settingKey, value) {
    setPluginSettings({
      ...pluginSettings,
      [pluginName]: {
        ...pluginSettings[pluginName],
        [settingKey]: value
      }
    });
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

  return (
    <>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2>Experiments</h2>
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
          <p>Loading experiments...</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: '40px' }}></th>
                <th>Name</th>
                <th>Description</th>
                <th>Tags</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {experiments.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', color: '#9ca3af' }}>
                    No experiments created
                  </td>
                </tr>
              ) : (
                experiments.map(exp => (
                  <tr key={exp._id}>
                    <td style={{ textAlign: 'center' }}>
                      <StarButton 
                        entityType="experiment"
                        entityId={exp._id}
                        isFavorite={exp.is_favorite || false}
                        size="small"
                        onToggle={(newFavoriteState, updatedEntity) => {
                          // Update the experiment in the local state
                          setExperiments(experiments.map(e => 
                            e._id === exp._id ? { ...e, is_favorite: newFavoriteState } : e
                          ));
                        }}
                      />
                    </td>
                    <td>
                      <Link href={`/experiments/${exp._id}`} style={{ fontWeight: 'bold' }}>
                        {exp.name}
                      </Link>
                    </td>
                    <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {exp.description || '-'}
                    </td>
                    <td>
                      {exp.tags && exp.tags.length > 0 ? (
                        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                          {exp.tags.map(tag => (
                            <span 
                              key={tag} 
                              style={{ 
                                background: '#374151', 
                                padding: '2px 6px', 
                                borderRadius: '4px', 
                                fontSize: '12px' 
                              }}
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td>{formatDate(exp.created_at)}</td>
                    <td>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <Link href={`/experiments/${exp._id}`} className="btn" style={{ fontSize: '16px', width: '32px', height: '32px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0', border: '1px solid #60a5fa' }} title="View">
                          ○
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
                          onClick={() => handleDeleteExperiment(exp._id, exp.name)}
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

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h3 style={{ margin: 0 }}>Create New Experiment</h3>
        </div>
        <form onSubmit={handleCreateExperiment}>
          <div style={{ marginBottom: '16px' }}>
            <input
              className="input"
              placeholder="Experiment name"
              value={form.name}
              onChange={e => setForm({...form, name: e.target.value})}
              required
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <textarea
              className="input"
              placeholder="Description (optional)"
              value={form.description}
              onChange={e => setForm({...form, description: e.target.value})}
              rows={3}
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <input
              className="input"
              placeholder="Tags (comma-separated, optional)"
              value={form.tags}
              onChange={e => setForm({...form, tags: e.target.value})}
            />
          </div>

          {/* Plugin Selection */}
          {plugins.length > 0 && (
            <div style={{ marginBottom: '24px' }}>
              <div style={{
                marginBottom: '16px',
                paddingBottom: '12px',
                borderBottom: '2px solid #374151'
              }}>
                <h4 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '8px', fontSize: '16px' }}>
                  <span style={{ fontSize: '20px' }}>🔌</span>
                  Experiment Plugins
                </h4>
                <p style={{
                  margin: '4px 0 0 0',
                  fontSize: '13px',
                  color: '#9ca3af'
                }}>
                  Optional automation tools to enhance your experiments
                </p>
              </div>

              <div style={{ display: 'grid', gap: '12px' }}>
                {plugins.map(plugin => (
                  <PluginCard
                    key={plugin.name}
                    plugin={plugin}
                    isSelected={selectedPlugins.includes(plugin.name)}
                    onToggle={togglePlugin}
                    pluginSettings={pluginSettings[plugin.name] || {}}
                    onSettingChange={(key, value) => updatePluginSetting(plugin.name, key, value)}
                  />
                ))}
              </div>

              {selectedPlugins.length > 0 && (
                <div style={{
                  marginTop: '16px',
                  padding: '12px 16px',
                  backgroundColor: '#1e3a5f',
                  borderRadius: '8px',
                  border: '2px solid #60a5fa'
                }}>
                  <div style={{
                    fontSize: '13px',
                    color: '#93c5fd',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    fontWeight: '500'
                  }}>
                    <span style={{ fontSize: '16px' }}>✓</span>
                    {selectedPlugins.length} plugin{selectedPlugins.length > 1 ? 's' : ''} enabled:
                    <span style={{ color: '#bfdbfe' }}>{selectedPlugins.join(', ')}</span>
                  </div>
                </div>
              )}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button className="btn" type="submit">
              Create Experiment
            </button>
          </div>
        </form>
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