'use client';
import { useEffect, useState } from 'react';
import { get } from "@/api/api-client";
import Link from 'next/link';

export default function HomePage() {
  const [stats, setStats] = useState({
    experiments: 0,
    revisions: 0,
    runs: 0,
    environments: 0,
    runningRuns: 0
  });
  const [recentRuns, setRecentRuns] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboardData();
  }, []);

  async function loadDashboardData() {
    try {
      const [experiments, revisions, runs, environments] = await Promise.all([
        get('/api/experiments'),
        get('/api/revisions'),
        get('/api/runs', { query: { limit: 10 } }),
        get('/api/environments')
      ]);

      const runsData = runs.runs || runs;
      const runningRuns = runsData.filter(r => r.status === 'running');

      setStats({
        experiments: experiments.length,
        revisions: revisions.length,
        runs: runs.total || runsData.length,
        environments: environments.length,
        runningRuns: runningRuns.length
      });

      setRecentRuns(runsData.slice(0, 5));
    } catch (e) {
      console.error('Error loading dashboard data:', e);
    } finally {
      setLoading(false);
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

  return (
    <>
      <div className="card">
        <h1>ArenaLab Dashboard</h1>
        <p style={{ color: '#9ca3af', marginBottom: '24px' }}>
          Platform for Unity ML-Agents experimentation{' '}
          <a
            href="https://github.com/icecoolinux/arenalab#approach"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#60a5fa', textDecoration: 'underline' }}
          >
            (Learn about our approach)
          </a>
        </p>

        {loading ? (
          <p>Loading statistics...</p>
        ) : (
          <>
            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', 
              gap: '16px', 
              marginBottom: '32px' 
            }}>
              <div style={{ 
                background: '#111827', 
                border: '1px solid #374151', 
                borderRadius: '8px', 
                padding: '20px',
                textAlign: 'center'
              }}>
                <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#60a5fa' }}>
                  {stats.experiments}
                </div>
                <div style={{ color: '#9ca3af', fontSize: '14px' }}>
                  Experiments
                </div>
                <Link href="/experiments" style={{ fontSize: '12px' }}>
                  View all →
                </Link>
              </div>

              <div style={{ 
                background: '#111827', 
                border: '1px solid #374151', 
                borderRadius: '8px', 
                padding: '20px',
                textAlign: 'center'
              }}>
                <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#10b981' }}>
                  {stats.revisions}
                </div>
                <div style={{ color: '#9ca3af', fontSize: '14px' }}>
                  Revisions
                </div>
                <Link href="/revisions" style={{ fontSize: '12px' }}>
                  View all →
                </Link>
              </div>

              <div style={{ 
                background: '#111827', 
                border: '1px solid #374151', 
                borderRadius: '8px', 
                padding: '20px',
                textAlign: 'center'
              }}>
                <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#f59e0b' }}>
                  {stats.runs}
                </div>
                <div style={{ color: '#9ca3af', fontSize: '14px' }}>
                  Total Runs
                </div>
                <Link href="/runs" style={{ fontSize: '12px' }}>
                  View all →
                </Link>
              </div>

              <div style={{ 
                background: '#111827', 
                border: '1px solid #374151', 
                borderRadius: '8px', 
                padding: '20px',
                textAlign: 'center'
              }}>
                <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#059669' }}>
                  {stats.runningRuns}
                </div>
                <div style={{ color: '#9ca3af', fontSize: '14px' }}>
                  Running Now
                </div>
                <Link href="/runs?status=running" style={{ fontSize: '12px' }}>
                  View active →
                </Link>
              </div>

              <div style={{ 
                background: '#111827', 
                border: '1px solid #374151', 
                borderRadius: '8px', 
                padding: '20px',
                textAlign: 'center'
              }}>
                <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#8b5cf6' }}>
                  {stats.environments}
                </div>
                <div style={{ color: '#9ca3af', fontSize: '14px' }}>
                  Unity Environments
                </div>
                <Link href="/environments" style={{ fontSize: '12px' }}>
                  View all →
                </Link>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
              <div>
                <h3>Quick Actions</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <Link href="/experiments" className="btn" style={{ justifyContent: 'flex-start' }}>
                    📊 Create New Experiment
                  </Link>
                  <Link href="/revisions/new" className="btn" style={{ justifyContent: 'flex-start' }}>
                    📝 New Revision
                  </Link>
                  <Link href="/runs/new" className="btn" style={{ justifyContent: 'flex-start' }}>
                    ▶️ New Run
                  </Link>
                  <Link href="/environments" className="btn" style={{ justifyContent: 'flex-start' }}>
                    🎮 Register Unity Environment
                  </Link>
                </div>
              </div>

              <div>
                <h3>Recent Runs</h3>
                {recentRuns.length === 0 ? (
                  <p style={{ color: '#9ca3af' }}>No recent runs</p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {recentRuns.map(run => (
                      <div 
                        key={run._id} 
                        style={{ 
                          display: 'flex', 
                          alignItems: 'center', 
                          justifyContent: 'space-between',
                          padding: '8px',
                          background: '#0b0f14',
                          border: '1px solid #374151',
                          borderRadius: '4px'
                        }}
                      >
                        <div>
                          <Link href={`/runs/${run._id}`} style={{ fontFamily: 'monospace', fontSize: '12px' }}>
                            {run._id.slice(-8)}
                          </Link>
                          <div style={{ fontSize: '10px', color: '#9ca3af' }}>
                            {formatDate(run.created_at)}
                          </div>
                        </div>
                        <span 
                          style={{ 
                            padding: '2px 6px', 
                            borderRadius: '4px', 
                            fontSize: '10px',
                            background: getStatusColor(run.status),
                            color: 'white'
                          }}
                        >
                          {run.status || 'unknown'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}