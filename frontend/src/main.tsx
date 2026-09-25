import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles/tokens.css'
import './styles/base.css'
import './styles/layout.css'
import './styles/components.css'
import './styles/pages.css'
import './styles/responsive.css'

const container = document.getElementById('root')
if (!container) {
  // 不 silent 地失败：index.html 里少了 #root 是低级但常见的错误
  throw new Error('Root container #root not found in index.html')
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
