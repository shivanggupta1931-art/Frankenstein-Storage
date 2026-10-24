import { api } from "../services/api";

/**
 * Returns the relative or direct URL for file preview.
 */
export function getPreviewUrl(fileId: string): string {
  return `/api/v1/files/${fileId}/preview`;
}

export { api };
export default api;
