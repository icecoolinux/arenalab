'use client';
import { useEffect, useState } from 'react';
import { getPlugins } from "@/api/api-client";
import Link from 'next/link';

export default function Plugins() {
  const [plugins, setPlugins] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedScope, setSelectedScope] = useState('all');

  useEffect(() => {
    loadPlugins();
  }, []);

  async function loadPlugins() {
    try {
      setLoading(true);
      setError('');
      const response = await getPlugins();
      setPlugins(response.plugins || []);
    } catch (e) {
      setError(`Error loading plugins: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }

  const filteredPlugins = selectedScope === 'all' 
    ? plugins 
    : plugins.filter(p => p.scope === selectedScope);

  const getScopeIcon = (scope) => {
    switch(scope) {
      case 'experiment': return '🧪';
      case 'run': return '🏃';
      case 'revision': return '📝';
      default: return '🔌';
    }
  };

  const getScopeColor = (scope) => {
    switch(scope) {
      case 'experiment': return 'bg-blue-100 text-blue-800';
      case 'run': return 'bg-green-100 text-green-800';  
      case 'revision': return 'bg-purple-100 text-purple-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-lg">Loading plugins...</div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-2">Available Plugins</h1>
        <p className="text-gray-400 mb-3">
          Discover and learn about plugins that can automate and enhance your ML experiments.
        </p>
        <div
          className="border-l-4 rounded-lg shadow-xl"
          style={{
            backgroundColor: 'rgba(30, 58, 138, 0.3)',
            borderLeftColor: '#60a5fa',
            margin: '12px 0',
            padding: '16px 20px'
          }}
        >
          <div className="flex items-start" style={{gap: '12px'}}>
            <div style={{color: '#e5e7eb'}}>
              <span className="text-xl" style={{paddingRight:"10px", flexShrink: 0}}>ℹ️</span>
              <span className="font-bold" style={{color: '#93c5fd'}}>Note: </span>
              <span>The plugin system for adding custom algorithms will be available in the next version of ArenaLab.</span>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-500 text-red-300 px-4 py-3 rounded-lg mb-6">
          {error}
        </div>
      )}

      {/* Filter by scope */}
      <div className="mb-6">
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setSelectedScope('all')}
            className={`btn ${selectedScope === 'all' ? 'border-blue-500 text-blue-400' : ''}`}
          >
            All ({plugins.length})
          </button>
          <button
            onClick={() => setSelectedScope('experiment')}
            className={`btn ${selectedScope === 'experiment' ? 'border-blue-500 text-blue-400' : ''}`}
          >
            🧪 Experiment ({plugins.filter(p => p.scope === 'experiment').length})
          </button>
          <button
            onClick={() => setSelectedScope('run')}
            className={`btn ${selectedScope === 'run' ? 'border-blue-500 text-blue-400' : ''}`}
          >
            🏃 Run ({plugins.filter(p => p.scope === 'run').length})
          </button>
          <button
            onClick={() => setSelectedScope('revision')}
            className={`btn ${selectedScope === 'revision' ? 'border-blue-500 text-blue-400' : ''}`}
          >
            📝 Revision ({plugins.filter(p => p.scope === 'revision').length})
          </button>
        </div>
      </div>

      {/* Plugin list */}
      {filteredPlugins.length === 0 ? (
        <div className="card text-center py-8">
          <div className="text-4xl mb-3">🔌</div>
          <h3 className="text-lg font-bold mb-1">No plugins found</h3>
          <p className="text-gray-400">
            {selectedScope === 'all'
              ? 'No plugins are currently available.'
              : `No ${selectedScope} plugins found.`
            }
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredPlugins.map((plugin) => (
            <div key={plugin.name} className="card">
              <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                <div className="flex-1 min-w-0">
                  {/* Header */}
                  <div className="mb-3">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-2xl">{getScopeIcon(plugin.scope)}</span>
                      <h3 className="text-lg font-bold">{plugin.name}</h3>
                    </div>
                    <div className="flex items-center ml-11">
                      <span className="text-xs px-2 py-1 rounded border border-gray-700 text-gray-400 whitespace-nowrap" style={{marginRight: '12px'}}>
                        {plugin.scope}
                      </span>
                      <span className="text-xs text-gray-500 whitespace-nowrap">v{plugin.version}</span>
                    </div>
                  </div>

                  {/* Description */}
                  <p className="text-sm text-gray-400 mb-3">
                    {plugin.description}
                  </p>

                  {/* Author */}
                  <div className="flex items-center gap-2 text-xs text-gray-500 mb-3 sm:mb-0">
                    <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20" width="16" height="16">
                      <path fillRule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clipRule="evenodd" />
                    </svg>
                    <span>{plugin.author}</span>
                  </div>

                  {/* Tags */}
                  {plugin.tags && plugin.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {plugin.tags.map((tag) => (
                        <span
                          key={tag}
                          className="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-400"
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex flex-row sm:flex-col gap-2 flex-shrink-0 w-full sm:w-auto">
                  <Link href={`/plugins/${plugin.name}`} className="btn text-sm whitespace-nowrap flex-1 sm:flex-none text-center">
                    View Details
                  </Link>
                  {plugin.scope === 'experiment' && (
                    <Link
                      href={`/experiments/new?plugin=${plugin.name}`}
                      className="btn text-sm whitespace-nowrap border-blue-500 text-blue-400 flex-1 sm:flex-none text-center"
                    >
                      Use in Experiment
                    </Link>
                  )}
                  {plugin.scope === 'run' && (
                    <Link
                      href={`/runs/new?plugin=${plugin.name}`}
                      className="btn text-sm whitespace-nowrap border-blue-500 text-blue-400 flex-1 sm:flex-none text-center"
                    >
                      Use in Run
                    </Link>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Plugin development info */}
      <div className="card mt-8">
        <h2 className="text-lg font-bold mb-2">
          🚀 Want to create your own plugin?
        </h2>
        <p className="text-gray-400 mb-4 text-sm">
          You can create your own plugins to extend ArenaLab functionality.
        </p>
        <a
          href="https://github.com/icecoolinux/arenalab/blob/main/docs/CONTRIBUTING.md"
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-400 hover:text-blue-300 text-sm"
        >
          📖 Learn more on GitHub →
        </a>
      </div>
    </div>
  );
}