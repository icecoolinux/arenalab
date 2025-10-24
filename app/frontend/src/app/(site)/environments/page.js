'use client';
import { useEffect, useState, useRef } from 'react';
import { getEnvironments, del, get, api, checkEnvironmentDependencies, deleteEnvironment as deleteEnvironmentApi } from "@/api/api-client";
import Link from 'next/link';
import DeleteConfirmationDialog from '@/components/DeleteConfirmationDialog';
import { useDeleteWithConfirmation } from '@/hooks/useDeleteWithConfirmation';

export default function Environments() {
  const [environments, setEnvironments] = useState([]);
  const [form, setForm] = useState({
    name: '',
    description: '',
    git_commit_url: '',
    nextVersion: null,
    basedOnEnv: null
  });
  const [selectedFile, setSelectedFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  // Delete confirmation hook
  const deleteHook = useDeleteWithConfirmation(
    checkEnvironmentDependencies,
    deleteEnvironmentApi,
    () => loadEnvironments(),
    (error) => setError(`Error deleting environment: ${error.message}`)
  );

  // Supported file formats
  const SUPPORTED_FORMATS = ['.zip', '.tar.gz', '.tgz', '.tar.bz2', '.tar'];

  async function loadEnvironments() {
    try {
      setLoading(true);
      setError('');
      const data = await getEnvironments();
      
      // Custom sorting: group by name, order groups by latest creation, versions descending
      const sortedData = sortEnvironmentsByNameAndCreation(data);
      setEnvironments(sortedData);
    } catch (e) {
      setError(`Error loading environments: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }

  function sortEnvironmentsByNameAndCreation(envs) {
    // Group environments by name
    const grouped = envs.reduce((acc, env) => {
      if (!acc[env.name]) {
        acc[env.name] = [];
      }
      acc[env.name].push(env);
      return acc;
    }, {});

    // Sort versions within each group (highest version first)
    Object.keys(grouped).forEach(name => {
      grouped[name].sort((a, b) => b.version - a.version);
    });

    // Get the latest created_at for each name group (from the most recent version)
    const nameGroups = Object.keys(grouped).map(name => ({
      name,
      environments: grouped[name],
      latestCreation: Math.max(...grouped[name].map(env => new Date(env.created_at).getTime()))
    }));

    // Sort name groups by latest creation (most recent first)
    nameGroups.sort((a, b) => b.latestCreation - a.latestCreation);

    // Flatten back to array
    return nameGroups.flatMap(group => group.environments);
  }

  function isLatestVersion(env, environments) {
    const sameNameEnvs = environments.filter(e => e.name === env.name);
    const maxVersion = Math.max(...sameNameEnvs.map(e => e.version));
    return env.version === maxVersion;
  }

  function getNextVersion(envName, environments) {
    const sameNameEnvs = environments.filter(e => e.name === envName);
    if (sameNameEnvs.length === 0) return 1;
    const maxVersion = Math.max(...sameNameEnvs.map(e => e.version));
    return maxVersion + 1;
  }

  useEffect(() => {
    loadEnvironments();
  }, []);

  function isValidFileFormat(filename) {
    const lowerName = filename.toLowerCase();
    return SUPPORTED_FORMATS.some(format => lowerName.endsWith(format));
  }

  function getFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  function handleFileSelect(file) {
    if (!file) return;

    // Validate file format
    if (!isValidFileFormat(file.name)) {
      setError(`Unsupported file format. Valid formats: ${SUPPORTED_FORMATS.join(', ')}`);
      return;
    }

    // Validate file size (1GB limit)
    const maxSize = 1024 * 1024 * 1024; // 1GB
    if (file.size > maxSize) {
      setError(`File too large. Maximum size: ${getFileSize(maxSize)}`);
      return;
    }

    setSelectedFile(file);
    setError('');
  }

  function handleDragOver(e) {
    e.preventDefault();
    setDragOver(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    setDragOver(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      handleFileSelect(files[0]);
    }
  }

  function handleFileInputChange(e) {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
      handleFileSelect(files[0]);
    }
  }

  function removeSelectedFile() {
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }

  async function uploadEnvironment(e) {
    e.preventDefault();

    if (!form.name.trim()) {
      setError('Environment name is required');
      return;
    }

    if (!selectedFile) {
      setError('You must select an environment file');
      return;
    }

    try {
      setError('');
      setUploading(true);
      setUploadProgress(0);

      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('name', form.name.trim());
      formData.append('description', form.description.trim());
      formData.append('git_commit_url', form.git_commit_url.trim());

      // Create XMLHttpRequest for progress tracking
      const xhr = new XMLHttpRequest();
      
      const uploadPromise = new Promise((resolve, reject) => {
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            const progress = Math.round((e.loaded / e.total) * 100);
            setUploadProgress(progress);
          }
        });

        xhr.addEventListener('load', () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              const response = JSON.parse(xhr.responseText);
              resolve(response);
            } catch (e) {
              resolve(xhr.responseText);
            }
          } else {
            reject(new Error(xhr.responseText || `HTTP ${xhr.status}`));
          }
        });

        xhr.addEventListener('error', () => {
          reject(new Error('Network error during upload'));
        });

        xhr.addEventListener('abort', () => {
          reject(new Error('Upload was cancelled'));
        });

        xhr.open('POST', '/api/environments/upload');
        
        // Set authorization header
        const token = localStorage.getItem('token');
        if (token) {
          xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        }

        xhr.send(formData);
      });

      await uploadPromise;

      // Reset form
      setForm({ name: '', description: '', git_commit_url: '', nextVersion: null, basedOnEnv: null });
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      setUploadProgress(0);
      
      // Reload environments
      loadEnvironments();
      
    } catch (e) {
      setError(`Error uploading environment: ${e.message}`);
      setUploadProgress(0);
    } finally {
      setUploading(false);
    }
  }

  function handleDeleteEnvironment(id, name) {
    deleteHook.initiateDelete(id, name, 'environment');
  }

  async function viewEnvironmentInfo(id) {
    try {
      const info = await get(`/api/environments/${id}/info`);
      // For now, just show an alert with the info
      // In a real app, you might want a modal or separate page
      const { environment, filesystem_info } = info;
      const details = [
        `Name: ${environment.name}`,
        `Version: v${environment.version}`,
        `Original file: ${environment.original_filename}`,
        `Format: ${environment.file_format}`,
        `Git Commit: ${environment.git_commit_url || 'Not specified'}`,
        `Size: ${filesystem_info.size_mb} MB`,
        `Status: ${filesystem_info.exists ? 'Available' : 'Not found'}`,
        `Path: ${environment.env_path}`
      ].join('\n');

      alert(`Environment Information:\n\n${details}`);
    } catch (e) {
      setError(`Error getting environment info: ${e.message}`);
    }
  }

  function handleNewVersion(env) {
    const nextVer = getNextVersion(env.name, environments);
    setForm({
      name: env.name,
      description: env.description,
      git_commit_url: env.git_commit_url || '',
      nextVersion: nextVer,
      basedOnEnv: env
    });
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    setError('');
    
    // Scroll to form
    setTimeout(() => {
      const formElement = document.querySelector('.upload-form');
      if (formElement) {
        formElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }, 100);
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
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h2>Unity ML-Agents Environments</h2>
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
          <p>Loading environments...</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Version</th>
                <th>Name</th>
                <th>Description</th>
                <th>Original File</th>
                <th>Format</th>
                <th>Git Commit</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {environments.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', color: '#9ca3af' }}>
                    No environments registered
                  </td>
                </tr>
              ) : (
                environments.map(env => (
                  <tr key={env._id}>
                    <td>
                      <span style={{ 
                        background: '#374151', 
                        padding: '2px 6px', 
                        borderRadius: '4px', 
                        fontSize: '12px',
                        fontFamily: 'monospace'
                      }}>
                        v{env.version}
                      </span>
                    </td>
                    <td style={{ fontWeight: 'bold' }}>{env.name}</td>
                    <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {env.description || '-'}
                    </td>
                    <td style={{ fontFamily: 'monospace', fontSize: '12px', color: '#9ca3af' }}>
                      {env.original_filename || 'N/A'}
                    </td>
                    <td>
                      {env.file_format && (
                        <span style={{
                          background: '#065f46',
                          color: '#10b981',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          fontSize: '11px',
                          fontFamily: 'monospace'
                        }}>
                          {env.file_format}
                        </span>
                      )}
                    </td>
                    <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {env.git_commit_url ? (
                        <a
                          href={env.git_commit_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            color: '#60a5fa',
                            textDecoration: 'none',
                            fontSize: '12px'
                          }}
                          title={env.git_commit_url}
                        >
                          {env.git_commit_url.includes('/commit/')
                            ? env.git_commit_url.split('/commit/')[1].substring(0, 7) + '...'
                            : 'View Commit'
                          }
                        </a>
                      ) : (
                        <span style={{ color: '#9ca3af', fontSize: '12px' }}>-</span>
                      )}
                    </td>
                    <td>{formatDate(env.created_at)}</td>
                    <td>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        {isLatestVersion(env, environments) && (
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
                              border: '1px solid #10b981'
                            }}
                            onClick={() => handleNewVersion(env)}
                            title="New Version"
                          >
                            +
                          </button>
                        )}
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
                            border: '1px solid #6b7280'
                          }}
                          onClick={() => viewEnvironmentInfo(env._id)}
                          title="Info"
                        >
                          i
                        </button>
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
                          onClick={() => handleDeleteEnvironment(env._id, env.name)}
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

      <div className="card upload-form">
        <h3>
          {form.basedOnEnv ?
            `New Version of "${form.basedOnEnv.name}"` :
            'Upload New Environment'
          }
        </h3>
        <p style={{ color: '#9ca3af', marginBottom: '16px' }}>
          Upload a compressed file (.zip, .tar.gz, .tgz, .tar.bz2) containing your Unity ML-Agents environment.
          The system will automatically extract the content and find the executable.
        </p>
        
        <form onSubmit={uploadEnvironment}>
          <div style={{ marginBottom: '16px' }}>
            <input
              className="input"
              placeholder="Environment name (e.g.: 3DBall-v1.0)"
              value={form.name}
              onChange={e => setForm({...form, name: e.target.value})}
              required
            />
          </div>

          {form.nextVersion && (
            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '4px', color: '#9ca3af', fontSize: '14px' }}>
                Version
              </label>
              <input
                className="input"
                value={`v${form.nextVersion}`}
                readOnly
                style={{
                  backgroundColor: '#374151',
                  color: '#9ca3af',
                  cursor: 'not-allowed'
                }}
              />
              {form.basedOnEnv && (
                <div style={{ marginTop: '4px', fontSize: '12px', color: '#6b7280' }}>
                  Based on: {form.basedOnEnv.name} v{form.basedOnEnv.version}
                </div>
              )}
            </div>
          )}

          <div style={{ marginBottom: '16px' }}>
            <textarea
              className="input"
              placeholder="Environment description (optional)"
              value={form.description}
              onChange={e => setForm({...form, description: e.target.value})}
              rows={2}
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <input
              className="input"
              placeholder="Git Commit URL (optional) - e.g.: https://github.com/user/repo/commit/abc123"
              value={form.git_commit_url}
              onChange={e => setForm({...form, git_commit_url: e.target.value})}
              type="url"
            />
          </div>
          
          {/* File Upload Area */}
          <div style={{ marginBottom: '16px' }}>
            <div 
              style={{
                border: `2px dashed ${dragOver ? '#10b981' : '#374151'}`,
                borderRadius: '8px',
                padding: '24px',
                textAlign: 'center',
                backgroundColor: dragOver ? '#064e3b' : '#1f2937',
                transition: 'all 0.2s',
                cursor: 'pointer'
              }}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              {selectedFile ? (
                <div>
                  <div style={{ color: '#10b981', marginBottom: '8px' }}>
                    📁 {selectedFile.name}
                  </div>
                  <div style={{ color: '#9ca3af', fontSize: '14px', marginBottom: '8px' }}>
                    {getFileSize(selectedFile.size)}
                  </div>
                  <button 
                    type="button"
                    style={{
                      background: '#dc2626',
                      color: 'white',
                      border: 'none',
                      padding: '4px 8px',
                      borderRadius: '4px',
                      fontSize: '12px',
                      cursor: 'pointer'
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      removeSelectedFile();
                    }}
                  >
                    Remove
                  </button>
                </div>
              ) : (
                <div>
                  <div style={{ color: '#9ca3af', marginBottom: '8px' }}>
                    📤 Drag your file here or click to select
                  </div>
                  <div style={{ color: '#6b7280', fontSize: '12px' }}>
                    Supported formats: {SUPPORTED_FORMATS.join(', ')}
                  </div>
                  <div style={{ color: '#6b7280', fontSize: '12px' }}>
                    Maximum size: 1GB
                  </div>
                </div>
              )}
            </div>
            
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip,.tar.gz,.tgz,.tar.bz2,.tar"
              onChange={handleFileInputChange}
              style={{ display: 'none' }}
            />
          </div>

          {/* Upload Progress */}
          {uploading && (
            <div style={{ marginBottom: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ fontSize: '14px', color: '#9ca3af' }}>Uploading...</span>
                <span style={{ fontSize: '14px', color: '#9ca3af' }}>{uploadProgress}%</span>
              </div>
              <div style={{ 
                width: '100%', 
                height: '8px', 
                backgroundColor: '#374151', 
                borderRadius: '4px',
                overflow: 'hidden'
              }}>
                <div style={{
                  width: `${uploadProgress}%`,
                  height: '100%',
                  backgroundColor: '#10b981',
                  transition: 'width 0.2s'
                }}></div>
              </div>
            </div>
          )}
          
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              className="btn"
              type="submit"
              disabled={uploading || !selectedFile}
              style={{
                opacity: (uploading || !selectedFile) ? 0.5 : 1,
                cursor: (uploading || !selectedFile) ? 'not-allowed' : 'pointer'
              }}
            >
              {uploading ? 'Uploading...' : (form.basedOnEnv ? 'Upload New Version' : 'Upload Environment')}
            </button>
          </div>
        </form>
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={deleteHook.isDialogOpen}
        onClose={deleteHook.cancelDelete}
        onConfirm={deleteHook.confirmDelete}
        title="Delete Environment"
        itemName={deleteHook.pendingDelete?.itemName}
        itemType="environment"
        warnings={deleteHook.warnings}
      />
    </>
  );
}