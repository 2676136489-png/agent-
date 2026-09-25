/**
 * 与后端 app/core/responses.py 的 ApiResponse 一一对应。
 *
 * [P0] 为什么手抄一遍类型而不是自动生成：
 * 自动生成（OpenAPI → TS）需要额外的构建步骤，Phase 1 只有 1 个接口，不值得。
 * 但这个文件的存在本身就是契约：后端改了响应结构，这里必须同步改，否则 TS 会报错。
 */

export interface ApiError {
  /** Machine readable code, e.g. 'not_found' | 'validation_error' | 'internal_error' */
  code: string
  message: string
  details?: unknown
}

export interface ApiResponse<T> {
  success: boolean
  data: T | null
  error: ApiError | null
}

export interface HealthData {
  status: string
  app_name: string
  environment: string
  version: string
  /** ISO-8601 string; JSON 没有 Date 类型，所以这里是 string */
  timestamp: string
}
