import { apiGet } from './client'
import type { HealthData } from '../types/api'

/** 每个领域一个文件，路由变化时只改这里，组件不受影响 */
export function fetchHealth(signal?: AbortSignal): Promise<HealthData> {
  return apiGet<HealthData>('/api/health', signal)
}
