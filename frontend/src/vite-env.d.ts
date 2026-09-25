/// <reference types="vite/client" />

// 显式声明我们会用到的环境变量，TS 才能在 import.meta.env 上给出类型提示，
// 也避免写错变量名时拿到 undefined 还不知道。
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
