import fs from 'node:fs'
const file = process.argv[2]
let s = fs.readFileSync(file, 'utf8')
// 去掉块注释，再逐行去掉行注释（忽略字符串内的 // 风险：探针脚本不使用含 // 的字符串）
s = s.replace(/\/\*[\s\S]*?\*\//g, '')
s = s.split('\n').map((line) => {
  const i = line.indexOf('//')
  return i >= 0 ? line.slice(0, i) : line
}).join(' ')
s = s.replace(/\s+/g, ' ').trim()
const out = file.replace(/\.js$/, '.min.js')
fs.writeFileSync(out, s)
console.log(out, s.length)
