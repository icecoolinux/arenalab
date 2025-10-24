'use client';

import { useEffect } from 'react';

/**
 * DeleteConfirmationDialog - A modal dialog for confirming delete operations with warnings
 * Can also be used as a generic confirmation dialog
 *
 * @param {Object} props
 * @param {boolean} props.isOpen - Whether the dialog is open
 * @param {function} props.onClose - Callback when dialog is closed
 * @param {function} props.onConfirm - Callback when delete is confirmed
 * @param {string} props.title - Dialog title
 * @param {string} props.message - Custom message (overrides default)
 * @param {string} props.itemName - Name of the item being deleted
 * @param {string} props.itemType - Type of item (experiment, revision, run, environment)
 * @param {string} props.confirmText - Text for confirm button (default: "Delete")
 * @param {string} props.confirmColor - Color for confirm button (default: "#ef4444")
 * @param {Object} props.warnings - Warnings object from dependency check API
 */
export default function DeleteConfirmationDialog({
  isOpen,
  onClose,
  onConfirm,
  title = 'Confirm Deletion',
  message = null,
  itemName,
  itemType,
  confirmText = null,
  confirmColor = '#ef4444',
  warnings = null
}) {
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

  if (!isOpen) return null;

  const hasWarnings = warnings?.has_warnings;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
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
          borderRadius: '8px',
          padding: '24px',
          maxWidth: '600px',
          width: '90%',
          maxHeight: '80vh',
          overflow: 'auto',
          boxShadow: '0 4px 6px rgba(0, 0, 0, 0.3)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ marginBottom: '16px' }}>
          <h2 style={{ margin: 0, fontSize: '20px', color: '#f1f5f9' }}>
            {title}
          </h2>
        </div>

        {/* Content */}
        <div style={{ marginBottom: '20px' }}>
          {message ? (
            <div style={{ margin: '0 0 12px 0', color: '#cbd5e1' }}>
              {message}
            </div>
          ) : (
            <>
              <p style={{ margin: '0 0 12px 0', color: '#cbd5e1' }}>
                Are you sure you want to delete{' '}
                <strong style={{ color: '#f1f5f9' }}>{itemName}</strong>?
              </p>

              <p style={{ margin: '0 0 16px 0', color: '#94a3b8', fontSize: '14px' }}>
                The {itemType} will be moved to the trash folder where it can potentially be recovered.
              </p>
            </>
          )}

          {/* Warnings */}
          {hasWarnings && (
            <div
              style={{
                backgroundColor: '#422006',
                border: '1px solid #f59e0b',
                borderRadius: '6px',
                padding: '12px',
                marginTop: '16px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontSize: '18px', marginRight: '8px' }}>⚠️</span>
                <strong style={{ color: '#fbbf24', fontSize: '14px' }}>
                  Warning: This action has dependencies
                </strong>
              </div>

              {warnings.warnings.map((warning, idx) => (
                <div key={idx} style={{ marginTop: '12px' }}>
                  <p style={{ margin: '0 0 8px 0', color: '#fcd34d', fontSize: '13px' }}>
                    {warning.message}
                  </p>

                  {warning.affected_items && warning.affected_items.length > 0 && (
                    <details style={{ marginTop: '8px' }}>
                      <summary
                        style={{
                          cursor: 'pointer',
                          color: '#94a3b8',
                          fontSize: '12px',
                          userSelect: 'none',
                        }}
                      >
                        View {warning.count} affected item{warning.count !== 1 ? 's' : ''}
                      </summary>
                      <ul
                        style={{
                          margin: '8px 0 0 0',
                          paddingLeft: '20px',
                          fontSize: '12px',
                          color: '#cbd5e1',
                        }}
                      >
                        {warning.affected_items.map((item, itemIdx) => (
                          <li key={itemIdx} style={{ marginBottom: '4px' }}>
                            {item.name || item.id}{' '}
                            {item.status && (
                              <span style={{ color: '#94a3b8' }}>({item.status})</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              border: '1px solid #475569',
              backgroundColor: '#334155',
              color: '#f1f5f9',
              cursor: 'pointer',
              fontSize: '14px',
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            style={{
              padding: '8px 16px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: confirmColor,
              color: '#fff',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: '500',
            }}
          >
            {confirmText || (hasWarnings ? 'Delete Anyway' : 'Delete')}
          </button>
        </div>
      </div>
    </div>
  );
}
