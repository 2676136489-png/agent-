import type { ApiResponse } from '../types/api'

/**
 * [P0] 唯一的 HTTP 出口。
 *
 * 为什么要把 fetch 包一层，而不是在组件里直接 fetch：
 * 1. baseURL、错误处理、超时只写一次
 * 2. 组件里不需要关心响应是信封格式还是裸数据
 * 3. 以后要加鉴权头、重试、埋点，只改这一个文件
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// [F1] 默认超时：启动一次研究工作流会跑 1~2 分钟，给足余量；
// 但也不能无限等，否则网络断开时 UI 会永远停在"执行中"。
const DEFAULT_TIMEOUT_MS = 300_000

/**
 * 拼出完整的后端地址。
 * SSE 用的是浏览器原生 EventSource，它不走 request()，需要绝对 URL。
 */
export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`
}

/** 所有请求都会被包成这个错误抛出，组件只需要 catch 一种类型 */
export class ApiClientError extends Error {
  readonly code: string
  readonly status: number
  readonly details?: unknown

  constructor(params: { message: string; code: string; status: number; details?: unknown }) {
    super(params.message)
    this.name = 'ApiClientError'
    this.code = params.code
    this.status = params.status
    this.details = params.details
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

/**
 * [F1] 把「外部 signal + 超时」合并成一个控制器。
 *
 * 之前这里只在注释里写了"用 AbortController 让请求可以被取消"，
 * 实际代码里根本没有创建过控制器：所有请求都无法取消、也没有超时，
 * 1~2 分钟的长请求在切换页面后仍会继续跑并尝试 setState。
 */
function withTimeout(
  external?: AbortSignal | null,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  const onExternalAbort = () => controller.abort()
  if (external) {
    if (external.aborted) controller.abort()
    else external.addEventListener('abort', onExternalAbort, { once: true })
  }

  const cleanup = () => {
    clearTimeout(timer)
    external?.removeEventListener('abort', onExternalAbort)
  }

  return { signal: controller.signal, cleanup }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const { signal, cleanup } = withTimeout(init?.signal, timeoutMs)

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal,
      headers: {
        Accept: 'application/json',
        ...init?.headers,
      },
    })
  } catch (error) {
    cleanup()
    if (isAbortError(error)) {
      throw new ApiClientError({
        message: '请求超时或已被取消，请重试',
        code: 'aborted',
        status: 0,
      })
    }
    // [F1] 网络层失败（后端未启动 / 断网）也要包成 ApiClientError，
    // 否则调用方 catch 到的是裸 TypeError，UI 无法给出可读提示。
    throw new ApiClientError({
      message: `无法连接后端（${API_BASE_URL}），请确认服务已启动`,
      code: 'network_error',
      status: 0,
    })
  }
  cleanup()

  let payload: ApiResponse<T> | null = null
  try {
    payload = (await response.json()) as ApiResponse<T>
  } catch {
    // 后端返回了非 JSON（例如网关的 HTML 错误页）
    throw new ApiClientError({
      message: '后端返回了非 JSON 响应，请确认 API_BASE_URL 指向的是后端服务',
      code: 'invalid_response',
      status: response.status,
    })
  }

  // 关键：HTTP 状态码和 body 里的 success 都要看。
  // 后端保证 success=false 时一定带 error，但反过来 4xx/5xx 也可能带 error。
  if (!response.ok || !payload.success) {
    throw new ApiClientError({
      message: payload?.error?.message ?? `请求失败（HTTP ${response.status}）`,
      code: payload?.error?.code ?? 'http_error',
      status: response.status,
      details: payload?.error?.details,
    })
  }

  if (payload.data === null) {
    throw new ApiClientError({
      message: '后端返回了空的 data',
      code: 'empty_data',
      status: response.status,
    })
  }

  return payload.data
}

export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { method: 'GET', signal })
}

export function apiPost<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
}

/** 文件上传：multipart 不能设置 Content-Type，交给浏览器自动带 boundary */
export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const formData = new FormData()
  formData.append('file', file)
  const { signal, cleanup } = withTimeout(undefined, DEFAULT_TIMEOUT_MS)

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      body: formData,
      signal,
    })
  } catch (error) {
    if (isAbortError(error)) {
      throw new ApiClientError({ message: '上传超时', code: 'aborted', status: 0 })
    }
    throw new ApiClientError({
      message: `无法连接后端（${API_BASE_URL}）`,
      code: 'network_error',
      status: 0,
    })
  } finally {
    cleanup()
  }

  // [F7] 复用与 request() 相同的错误分支：非 JSON 响应不再抛裸 SyntaxError
  let payload: ApiResponse<T> | null = null
  try {
    payload = (await response.json()) as ApiResponse<T>
  } catch {
    throw new ApiClientError({
      message: '后端返回了非 JSON 响应',
      code: 'invalid_response',
      status: response.status,
    })
  }

  if (!response.ok || !payload.success) {
    throw new ApiClientError({
      message: payload?.error?.message ?? `上传失败（HTTP ${response.status}）`,
      code: payload?.error?.code ?? 'http_error',
      status: response.status,
    })
  }
  return payload.data as T
}
