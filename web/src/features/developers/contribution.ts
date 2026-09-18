export type ContributionLocale = 'zh' | 'en'

export type ContributionCopy = {
  label: string
  title: string
  body: string
  detail: string
}

export const contributionCopy: Record<ContributionLocale, {
  eyebrow: string
  heading: string
  intro: string
  cards: ContributionCopy[]
  promptTitle: string
  promptIntro: string
  copyPrompt: string
  copied: string
  copyFailed: string
  docs: string
  token: string
  bounds: string
  boundsBody: string
}> = {
  zh: {
    eyebrow: 'AI CO-DESIGN',
    heading: '让 AI 做研究工作',
    intro: 'AI 可以提案、优化和分析证据；Arena 负责校验 FlySpec、执行固定运行时，并保留可复核结果。',
    cards: [
      {label: '01 / PROPOSE', title: '提出 FlySpec', body: '让模型阅读季规则和当前设计，生成有限的权重或神经元参数变更。', detail: '先调用 /flies/validate；预算由服务器计算。'},
      {label: '02 / OPTIMIZE', title: '外部优化器', body: '在你的机器上运行搜索、进化或便宜的本地模型，逐个提交候选。', detail: '使用 /training/{id}/candidates；候选仍由固定运行时评测。'},
      {label: '03 / ANALYZE', title: '分析真实证据', body: '读取已验证比赛的 frames、events、receipt 和 neural traces，比较行为与轨迹。', detail: '只分析已生成的回放，不会自动启动计算。'},
    ],
    promptTitle: '给 AI 的任务提示',
    promptIntro: '复制后交给你的模型；它不会包含 API token。',
    copyPrompt: '复制任务提示',
    copied: '已复制任务提示',
    copyFailed: '复制失败，请手动选择文本',
    docs: '打开公开 API 文档',
    token: '查看我的 API 身份',
    bounds: '当前可设计什么',
    boundsBody: '当前使用固定 LIF 神经运行时，没有在线学习，也不托管任意代码。外部优化器只能提交经过校验的 FlySpec 候选；它不是任意神经模型运行环境。',
  },
  en: {
    eyebrow: 'AI CO-DESIGN',
    heading: 'Give AI useful research work',
    intro: 'AI can propose, optimize, and analyze evidence. Arena validates FlySpec, runs the fixed runtime, and keeps results reviewable.',
    cards: [
      {label: '01 / PROPOSE', title: 'Propose a FlySpec', body: 'Have a model read the season rules and current design, then produce bounded weight or neuron-parameter edits.', detail: 'Call /flies/validate first; the server computes the budget.'},
      {label: '02 / OPTIMIZE', title: 'Run an external optimizer', body: 'Run search, evolution, or a low-cost local model on your machine and submit candidates one at a time.', detail: 'Use /training/{id}/candidates; the fixed runtime evaluates every candidate.'},
      {label: '03 / ANALYZE', title: 'Analyze real evidence', body: 'Read verified match frames, events, receipts, and neural traces to compare behavior and trajectories.', detail: 'This analyzes existing replay evidence; it does not start compute automatically.'},
    ],
    promptTitle: 'Task prompt for an AI model',
    promptIntro: 'Copy it into your model; it contains no API token.',
    copyPrompt: 'Copy task prompt',
    copied: 'Task prompt copied',
    copyFailed: 'Copy failed; select the text manually',
    docs: 'Open public API docs',
    token: 'View my API identity',
    bounds: 'What you can design today',
    boundsBody: 'The current runtime is fixed LIF, with no online learning and no hosted arbitrary code. An external optimizer submits validated FlySpec candidates; it is not an arbitrary neural-model runtime.',
  },
}

export function buildContributionPrompt(origin: string, locale: ContributionLocale): string {
  const language = locale === 'zh' ? '请用简洁中文回答，必要时保留英文 API 名称。' : 'Answer in concise English and keep API names exact.'
  return `${language}

You are contributing to Fly Arena at ${origin}.
Public docs: ${origin}/docs
Standalone agent guide: ${origin}/api/v1/agent-guide
OpenAPI schema: ${origin}/openapi.json
API base: ${origin}/api/v1

Choose one bounded task:
1. Propose a FlySpec: GET /season, GET /flies, then POST /flies/validate. Return a minimal JSON patch or complete FlySpec with bounded weight mutations or neuron parameters and explain its budget.
2. Implement an external optimizer on the user's machine using POST /training and POST /training/{id}/candidates. Keep the default session small and forage-only: population 2, generations 2, max evaluations/budget 4, duration 1 second, one map and seed. Use scripts/custom_strategy.py as the reference.
3. Analyze actual evidence from GET /matches/{id} and verified artifacts /matches/{id}/frames, /events, /receipt. Report observed metrics and uncertainty; do not invent traces or improvement claims.

Constraints:
- Do not start compute automatically. If the user has already authorized the bounded task and supplied a finite budget, proceed; ask only when the task or budget is missing.
- Use the user's existing local/session credentials only through their environment; never request, print, store, or embed a token in code or chat.
- The server validates budgets and FlySpec. The runtime is fixed LIF: no online learning, hosted arbitrary code, or arbitrary neural-model execution.
- External optimization proposes validated FlySpec candidates; it does not change the Arena runtime.
- Prefer cheap, incremental work and return exact commands, endpoint paths, and a reviewable next step.`
}
