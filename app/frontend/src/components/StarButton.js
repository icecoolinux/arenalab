'use client';
import { useState } from 'react';
import {
  toggleExperimentFavorite,
  toggleRevisionFavorite,
  toggleRunFavorite
} from '@/api/api-client';

export default function StarButton({ 
  entityType, 
  entityId, 
  isFavorite, 
  onToggle, 
  size = 'medium',
  disabled = false 
}) {
  const [isLoading, setIsLoading] = useState(false);
  const [localFavorite, setLocalFavorite] = useState(isFavorite);

  const handleClick = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (disabled || isLoading) return;

    try {
      setIsLoading(true);
      
      // Optimistically update UI
      const newFavoriteState = !localFavorite;
      setLocalFavorite(newFavoriteState);

      // Make API call based on entity type
      let updatedEntity;
      if (entityType === 'experiment') {
        updatedEntity = await toggleExperimentFavorite(entityId);
      } else if (entityType === 'revision') {
        updatedEntity = await toggleRevisionFavorite(entityId);
      } else if (entityType === 'run') {
        updatedEntity = await toggleRunFavorite(entityId);
      }

      // Update with server response
      setLocalFavorite(updatedEntity.is_favorite);
      
      // Notify parent component if callback provided
      if (onToggle) {
        onToggle(updatedEntity.is_favorite, updatedEntity);
      }
      
    } catch (error) {
      // Revert optimistic update on error
      setLocalFavorite(isFavorite);
      console.error(`Error toggling ${entityType} favorite:`, error);
    } finally {
      setIsLoading(false);
    }
  };

  const getSizeStyles = (size) => {
    switch (size) {
      case 'small':
        return {
          fontSize: '18px',
          padding: '2px',
          minWidth: '22px',
          minHeight: '22px'
        };
      case 'large':
        return {
          fontSize: '28px',
          padding: '8px',
          minWidth: '40px',
          minHeight: '40px'
        };
      default: // medium
        return {
          fontSize: '24px',
          padding: '6px',
          minWidth: '32px',
          minHeight: '32px'
        };
    }
  };

  const sizeStyles = getSizeStyles(size);
  const isCurrentlyFavorite = localFavorite;

  return (
    <button
      onClick={handleClick}
      disabled={disabled || isLoading}
      title={isCurrentlyFavorite ? 'Remove from favorites' : 'Add to favorites'}
      style={{
        ...sizeStyles,
        background: 'transparent',
        border: 'none',
        cursor: disabled || isLoading ? 'not-allowed' : 'pointer',
        color: isCurrentlyFavorite ? '#fbbf24' : '#6b7280', // amber-400 when favorite, gray-500 when not
        opacity: disabled ? 0.5 : isLoading ? 0.7 : 1,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: '4px',
        transition: 'all 0.2s ease',
        ...((!disabled && !isLoading) && {
          ':hover': {
            color: isCurrentlyFavorite ? '#f59e0b' : '#fbbf24', // darker amber on hover
            backgroundColor: 'rgba(251, 191, 36, 0.1)' // subtle amber background on hover
          }
        })
      }}
      onMouseEnter={(e) => {
        if (!disabled && !isLoading) {
          e.target.style.color = isCurrentlyFavorite ? '#f59e0b' : '#fbbf24';
          e.target.style.backgroundColor = 'rgba(251, 191, 36, 0.1)';
        }
      }}
      onMouseLeave={(e) => {
        if (!disabled && !isLoading) {
          e.target.style.color = isCurrentlyFavorite ? '#fbbf24' : '#6b7280';
          e.target.style.backgroundColor = 'transparent';
        }
      }}
    >
      {isLoading ? (
        <span style={{ animation: 'spin 1s linear infinite' }}>⭐</span>
      ) : (
        <span>{isCurrentlyFavorite ? '★' : '☆'}</span>
      )}
    </button>
  );
}