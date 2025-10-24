'use client';

import { useState } from 'react';

/**
 * Custom hook for handling delete operations with dependency checking and confirmation
 *
 * @param {function} checkDependenciesFn - Function to check dependencies (e.g., checkExperimentDependencies)
 * @param {function} deleteFn - Function to perform delete (e.g., deleteExperiment)
 * @param {function} onSuccess - Callback after successful deletion
 * @param {function} onError - Callback on error (optional)
 */
export function useDeleteWithConfirmation(
  checkDependenciesFn,
  deleteFn,
  onSuccess,
  onError
) {
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [warnings, setWarnings] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);

  /**
   * Initiate delete - checks dependencies and opens dialog
   */
  async function initiateDelete(itemId, itemName, itemType) {
    try {
      // Check dependencies
      const dependencyData = await checkDependenciesFn(itemId);

      setPendingDelete({ itemId, itemName, itemType });
      setWarnings(dependencyData);
      setIsDialogOpen(true);
    } catch (error) {
      console.error('Error checking dependencies:', error);
      if (onError) onError(error);
    }
  }

  /**
   * Confirm and execute delete
   */
  async function confirmDelete() {
    if (!pendingDelete) return;

    setIsDeleting(true);
    try {
      // Call delete with confirmed=true
      await deleteFn(pendingDelete.itemId, true);

      // Success
      setIsDialogOpen(false);
      setPendingDelete(null);
      setWarnings(null);

      if (onSuccess) onSuccess(pendingDelete);
    } catch (error) {
      console.error('Error deleting:', error);
      if (onError) onError(error);
    } finally {
      setIsDeleting(false);
    }
  }

  /**
   * Cancel delete
   */
  function cancelDelete() {
    setIsDialogOpen(false);
    setPendingDelete(null);
    setWarnings(null);
  }

  return {
    isDialogOpen,
    pendingDelete,
    warnings,
    isDeleting,
    initiateDelete,
    confirmDelete,
    cancelDelete,
  };
}
